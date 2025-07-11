#!/usr/bin/env python3

"""
Optical Flow based motion estimation module

This module handles Optical Flow estimation using a downward facing camera.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any
import base64

REV_FLOW = False
# Get logger
logger = logging.getLogger("opticalflow")

# previous image
prev_image: np.ndarray = None
prev_image_time = None


def get_optical_flow(curr_image: np.ndarray, capture_time, include_augmented_image: bool) -> Dict[str, Any]:
    """
    Estimate optical flow in the image using the Lucas-Kanade method and Shi-Tomasi corner detection.
    Optimized for speed with reduced image size, fewer features, and faster parameters.

    Args:
        image: Input image as numpy array (BGR format from OpenCV)
        prev_image: Previous image for optical flow calculation
        include_augmented_image: Whether to return augmented image with optical flow vectors drawn

    Returns:
        Dictionary containing:
        - success: bool indicating if detection was successful
        - flow_x: average flow value in x axis (None on failure)
        - flow_y: average flow value in y axis (None on failure)
        - dt: Time difference between current and previous image in seconds (None on failure)
        - message: Status message
        - image_base64: Base64 encoded image, None if not requested or could not be generated
    """

    # logging prefix for all messages from this function
    logging_prefix_str = "get_optical_flow:"

    import time
    start_time = time.time()

    try:
        # variables
        global prev_image, prev_image_time

        # Convert new image to grayscale for corner detection
        if len(curr_image.shape) == 3:
            curr_image_grey = cv2.cvtColor(curr_image, cv2.COLOR_BGR2GRAY)
        else:
            curr_image_grey = curr_image

        # OPTIMIZATION 1: Use center crop to reduce processing area
        # Use center 60% of the image for better performance
        h, w = curr_image_grey.shape
        crop_factor = 0.6
        crop_h = int(h * crop_factor)
        crop_w = int(w * crop_factor)
        start_y = (h - crop_h) // 2
        start_x = (w - crop_w) // 2
        curr_image_grey = curr_image_grey[start_y:start_y+crop_h, start_x:start_x+crop_w]

        # OPTIMIZATION 2: Reduce image resolution by 50% for faster processing
        curr_image_grey = cv2.resize(curr_image_grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)

        # if no previous image, backup current image to previous and return failure
        if prev_image is None:
            # backup current image to previous
            prev_image = curr_image_grey
            prev_image_time = capture_time

            # log and return failure
            logger.debug(f"{logging_prefix_str} No previous image available for optical flow calculation")
            return {
                "success": False,
                "message": "No previous image available",
                "flow_x": None,
                "flow_y": None,
                "dt": None,
                "image_base64": None
            }

        # OPTIMIZATION 3: Reduce number of features and optimize parameters for speed
        # Reduced maxCorners from 100 to 50 for faster processing
        feature_params = dict(maxCorners=50, qualityLevel=0.2, minDistance=10, blockSize=5)

        # OPTIMIZATION 4: Optimize Lucas-Kanade parameters for speed
        # Reduced winSize from (21,21) to (15,15) and maxLevel from 3 to 2
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03)
        lk_params = dict(winSize=(15, 15), maxLevel=2, criteria=criteria)

        # Detect corners in the previous image
        corner_start = time.time()
        corners0 = cv2.goodFeaturesToTrack(prev_image, mask=None, **feature_params)
        corner_time = time.time() - corner_start

        # If no corners detected, return failure
        if corners0 is None or len(corners0) == 0:
            # backup current image so it can be used on next iteration
            dt = capture_time - prev_image_time
            prev_image = curr_image_grey
            prev_image_time = capture_time
            logger.warning(f"{logging_prefix_str} No corners detected in the previous image")
            return {
                "success": False,
                "message": "No corners detected in the previous image",
                "flow_x": None,
                "flow_y": None,
                "dt": dt,
                "image_base64": None
            }

        # Calculate optical flow using Lucas-Kanade method
        lk_start = time.time()
        corners1, st, err = cv2.calcOpticalFlowPyrLK(prev_image, curr_image_grey, corners0, None, **lk_params)
        lk_time = time.time() - lk_start

        # OPTIMIZATION 5: Reduce retry threshold and use faster parameters for retry
        # Try again if less than 5 points were tracked (reduced from 10)
        if np.sum(st) < 5:
            # Use faster parameters for retry
            retry_start = time.time()
            corners1, st, err = cv2.calcOpticalFlowPyrLK(prev_image, curr_image_grey, corners0, None,
                                                         winSize=(12, 12), maxLevel=1)
            lk_time += time.time() - retry_start

        if REV_FLOW:
            # Use optimized parameters for reverse flow check
            rev_corners1, stRev, errRev = cv2.calcOpticalFlowPyrLK(
                curr_image_grey, prev_image, corners1, corners0, winSize=(12, 12), maxLevel=1, criteria=criteria)

            dist = np.linalg.norm(corners0 - rev_corners1, axis=1)
            st = st & stRev * (dist <= 0.5)

        # Use of previous image complete, backup current image to previous
        dt = capture_time - prev_image_time
        prev_image = curr_image_grey
        prev_image_time = capture_time

        # Calculate flow vectors for all tracked points
        good_new = corners1[st.ravel() == 1]
        good_old = corners0[st.ravel() == 1]
        good_errors = err[st.ravel() == 1]

        # Sanity check shapes
        if good_new.shape != good_old.shape or good_new.shape[0] == 0:
            logger.error(f"{logging_prefix_str} Invalid points array shapes, new:{good_new.shape}, "
                         f"old:{good_old.shape}, errors:{good_errors.shape}")
            return {
                "success": False,
                "message": "Invalid points array shapes",
                "flow_x": None,
                "flow_y": None,
                "dt": None,
                "image_base64": None
            }

        # Compute flow vectors and reshape to (N, 2)
        flow_vectors = (good_new - good_old).reshape(-1, 2)

        # print out shape of flow vectors
        logger.debug(f"{logging_prefix_str} good_new shape: {good_new.shape}, "
                     f"good_old shape: {good_old.shape}, good_errors shape: {good_errors.shape}"
                     f", flow_vectors shape: {flow_vectors.shape}")

        # Check if any points were successfully tracked
        if len(flow_vectors) == 0:
            logger.warning(f"{logging_prefix_str} No points successfully tracked")
            return {
                "success": False,
                "message": "No points successfully tracked",
                "flow_x": None,
                "flow_y": None,
                "dt": None,
                "image_base64": None
            }

        # Calculate weighted average flow rates in x and y axis
        # Use inverse of error as weights (lower error = higher weight)
        # Add small epsilon to avoid division by zero
        weights = 1.0 / (good_errors.ravel() + 1e-6)
        flow_x = np.average(flow_vectors[:, 0], weights=weights) if len(flow_vectors) > 0 else 0
        flow_y = np.average(flow_vectors[:, 1], weights=weights) if len(flow_vectors) > 0 else 0

        # OPTIMIZATION 6: Scale flow values back to original image coordinates
        # We scaled down by 0.5, so scale flow back up by 2.0
        flow_x = flow_x * 2.0
        flow_y = flow_y * 2.0

        # Convert numpy types to Python native types for JSON serialization
        flow_x = float(flow_x)
        flow_y = float(flow_y)
        dt = float(dt)

        # Log timing information
        total_time = time.time() - start_time
        logger.debug(f"{logging_prefix_str} INTERNAL_TIMING: Total:{total_time*1000:.1f}ms "
                     f"CornerDetect:{corner_time*1000:.1f}ms LK:{lk_time*1000:.1f}ms "
                     f"Features:{len(good_new)}")

        # Create augmented image
        image_base64 = None
        if include_augmented_image:
            # Use the original curr_image for visualization, but scale flow vectors appropriately
            augmented_image = curr_image.copy()

            # Scale coordinates back to original image size
            scale_factor = 2.0  # We scaled down by 0.5, so scale back up by 2.0
            h_orig, w_orig = curr_image.shape[:2]
            h_crop, w_crop = int(h_orig * 0.6), int(w_orig * 0.6)
            offset_y, offset_x = (h_orig - h_crop) // 2, (w_orig - w_crop) // 2

            for i, (new, old) in enumerate(zip(good_new, good_old)):
                # Scale coordinates back to original image coordinates
                a, b = new.ravel() * scale_factor
                c, d = old.ravel() * scale_factor

                # Add crop offset
                a, b = a + offset_x, b + offset_y
                c, d = c + offset_x, d + offset_y

                # Convert coordinates to integers for OpenCV drawing functions
                a, b, c, d = int(a), int(b), int(c), int(d)

                # Only draw if coordinates are within image bounds
                if 0 <= a < w_orig and 0 <= b < h_orig and 0 <= c < w_orig and 0 <= d < h_orig:
                    cv2.line(augmented_image, (a, b), (c, d), (0, 255, 0), 2)
                    cv2.circle(augmented_image, (a, b), 5, (0, 0, 255), -1)

            _, buffer = cv2.imencode('.jpg', augmented_image)
            image_base64 = base64.b64encode(buffer).decode('utf-8')

        # return success
        return {
            "success": True,
            "message": "Success",
            "flow_x": flow_x,
            "flow_y": flow_y,
            "dt": dt,
            "image_base64": image_base64
        }

    except Exception as e:
        logger.exception(f"Error during Optical Flow calculation: {str(e)}")
        return {
            "success": False,
            "message": f"Optical Flow calculation failed: {str(e)}",
            "flow_x": None,
            "flow_y": None,
            "dt": None,
            "image_base64": None
        }
