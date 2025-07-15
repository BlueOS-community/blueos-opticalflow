#!/usr/bin/env python3

# Optical Flow Python backend
# Implements these features required by the index.html frontend:
# - Save camera settings including type and RTSP URL
# - Get camera settings including last used settings
# - Save/get opticalflow enabled state (persistent across restarts)
# - "Test" button to view the live video and calculate flow values
# - "Run" button to enable the opticalflow including sending MAVLink messages to the vehicle
# - Status endpoint to check if opticalflow is currently running

import logging.handlers
import sys
import asyncio
import time
import math
import cv2
import base64
from math import tan, atan, radians, degrees
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi import Query
from typing import Dict, Any

# Import the local modules
from app import settings
from app import image_capture
from app import mavlink_interface
from app import optflow_lkt

# Configure console logging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Create logger
logger = logging.getLogger("opticalflow")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)

app = FastAPI()


# Global exception handler to ensure all errors return JSON
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in {request.url}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal server error: {str(exc)}",
            "error": "Internal server error"
        }
    )

# Global variables
opticalflow_running = False  # True if opticalflow is currently running
gimbal_down_q = [0.7071, 0, -0.7071, 0]  # Quaternion used to check for downward facing gimbal

# log that the backend has started
logger.info("Optical flow backend started")


# Auto-start opticalflow if it was previously enabled
async def startup_auto_restart():
    """Check if opticalflow was previously enabled and auto-restart if needed"""

    # logging prefix for all messages from this function
    logging_prefix_str = "opticalflow:"

    try:
        enabled = settings.get_opticalflow_enabled()
        if enabled:
            logger.info(f"{logging_prefix_str} auto-restarting")

            # Get last used settings for auto-restart
            last_used = settings.get_last_used()
            camera_type = last_used.get("camera_type")
            rtsp_url = last_used.get("rtsp")
            if not camera_type or not rtsp_url:
                logger.error(f"{logging_prefix_str} auto-restart failed, could not retrieve camera settings")
                return

            # call startup function in a background thread
            asyncio.create_task(start_opticalflow_internal(camera_type, rtsp_url))

    except Exception as e:
        logger.error(f"{logging_prefix_str} error during auto-restart: {str(e)}")


# Internal function to start optical flow
async def start_opticalflow_internal(camera_type: str, rtsp_url: str):
    """Internal function to start the opticalflow process"""
    global opticalflow_running

    # logging prefix for all messages from this function
    logging_prefix_str = "opticalflow:"

    try:
        logger.info(f"{logging_prefix_str} started")
        opticalflow_running = True

        # Send status message to ground station
        mavlink_interface.send_statustext_msg(settings.get_mavlink_sysid(), "OpticalFlow: started")

        # Get camera setting
        camera_hfov = settings.get_camera_horizontal_fov(camera_type)

        # Get MAVLink target system ID from settings
        target_system_id = settings.get_mavlink_sysid()

        # Get gimbal attitude usage setting
        use_gimbal_attitude = settings.get_gimbal_attitude_settings()

        # log settings used
        logger.info(f"{logging_prefix_str} Camera type: {camera_type}, HFOV: {camera_hfov}, RTSP:{rtsp_url}, SysId:{target_system_id}, UseGimbalAttitude:{use_gimbal_attitude}")

        # Testing capturing frame from RTSP stream
        frame_result = image_capture.capture_frame_from_stream(rtsp_url)
        if not frame_result["success"]:
            logger.error(f"{logging_prefix_str} failed to capture frame: {frame_result['message']}")
            opticalflow_running = False
            return

        # Test MAV2Rest connection by sending a test OPTICAL_FLOW message
        mav_test = mavlink_interface.send_optical_flow_msg(
            sysid=target_system_id,
            flow_x=0.0,
            flow_y=0.0,
            flow_comp_m_x=0.0,
            flow_comp_m_y=0.0,
            quality=0,
            ground_distance=-1,
            flow_rate_x=0.0,
            flow_rate_y=0.0
        )
        if not mav_test["success"]:
            logger.error(f"{logging_prefix_str} MAV2Rest connection test failed: {mav_test['message']}")
            opticalflow_running = False
            return

        # get gimbal attitude, if not available request it
        gimbal_result = mavlink_interface.get_gimbal_attitude(target_system_id)
        if not gimbal_result["success"]:
            # request gimbal attitude status at 1hz
            mavlink_interface.request_gimbal_attitude_status(target_system_id, 1)
            logger.info(f"{logging_prefix_str} Requested GIMBAL_DEVICE_ATTITUDE_STATUS at 1hz")

        # Send status text that optical flow is running
        mavlink_interface.send_statustext_msg(target_system_id, "OpticalFlow: running")

        # Optical flow main loop
        last_frame_time = time.time()
        last_log_time = last_frame_time
        last_send_time = last_frame_time
        frame_count = 0
        sent_count = 0

        # Track last frame capture time to avoid processing the same frame multiple times
        last_frame_capture_time = 0.0

        while opticalflow_running:
            try:
                # Start timing for the entire loop iteration
                loop_start_time = time.time()

                # Capture frame from RTSP stream
                frame_start_time = time.time()
                frame_result = image_capture.capture_frame_from_stream(rtsp_url, last_frame_capture_time)
                frame_capture_time = time.time() - frame_start_time

                if not frame_result["success"]:
                    logger.warning(f"{logging_prefix_str} failed to capture frame: {frame_result['message']}")

                    # if no frames captured in 10 seconds, restart the capture
                    if time.time() - last_frame_time > 10:
                        logger.error(f"{logging_prefix_str} No frames captured in 10 seconds, restarting capture")
                        image_capture.cleanup_video_capture()
                        last_frame_time = time.time()

                    # Wait 0.01 seconds before retrying
                    await asyncio.sleep(0.01)
                    continue

                # Get frame capture time and check if it's new
                last_frame_capture_time = frame_result.get("capture_time", time.time())

                # record success
                last_frame_time = time.time()
                frame_count += 1

                # Check if we should use gimbal attitude and if gimbal is facing downward
                # Defaults to sending target if gimbal attitude is unavailable
                should_send_target = True
                gimbal_check_time = 0.0
                if use_gimbal_attitude:
                    gimbal_start_time = time.time()
                    gimbal_result = mavlink_interface.get_gimbal_attitude(target_system_id)
                    gimbal_check_time = time.time() - gimbal_start_time

                    if gimbal_result["success"]:
                        # Use quaternion to check if gimbal is facing downward within 10 degrees
                        gimbal_attitude_dict = gimbal_result["quaternion"]
                        # Convert dictionary format to array format [w, x, y, z]
                        gimbal_attitude_q = [
                            gimbal_attitude_dict["w"],
                            gimbal_attitude_dict["x"],
                            gimbal_attitude_dict["y"],
                            gimbal_attitude_dict["z"]
                        ]
                        angle_diff_rad = angle_between_quaternions(gimbal_down_q, gimbal_attitude_q)
                        angle_diff_deg = degrees(angle_diff_rad)
                        logger.debug(f"{logging_prefix_str} Gimbal attitude angle_diff:{angle_diff_deg:.1f} deg")
                        if angle_diff_rad > radians(10):
                            should_send_target = False
                            logger.debug(f"{logging_prefix_str} Gimbal attitude angle_diff:{angle_diff_deg:.1f} > 10, skipping target")
                    else:
                        # If we can't get gimbal attitude but it's required, send anyway
                        logger.warning(f"{logging_prefix_str} gimbal attitude unavailable, sending anyway")

                optflow_calc_time = 0.0
                mavlink_send_time = 0.0

                if should_send_target:
                    # Get the captured frame
                    frame = frame_result["frame"]
                    width = frame_result["width"]
                    height = frame_result["height"]

                    # Perform optical flow calculation
                    optflow_start_time = time.time()
                    opticalflow_result = optflow_lkt.get_optical_flow(frame, last_frame_capture_time, False)
                    optflow_calc_time = time.time() - optflow_start_time

                    # calculate hfov
                    camera_vfov = calculate_vertical_fov(camera_hfov, width, height)

                    if opticalflow_result.get("success"):
                        # Extract flow values in pixels
                        flow_x_dpi = opticalflow_result.get("flow_x", 0.0)
                        flow_y_dpi = opticalflow_result.get("flow_y", 0.0)
                        dt = opticalflow_result.get("dt", 0.0)

                        # Convert pixel flow to angular flow (radians/second)
                        # Assuming a simple conversion based on camera FOV and frame rate
                        pixels_per_radian_h = width / math.radians(camera_hfov)
                        pixels_per_radian_v = height / math.radians(camera_vfov)

                        if dt > 0 and dt < 0.2:
                            # convert flow to radians/second
                            flow_x_rads = flow_x_dpi / (pixels_per_radian_h * dt)
                            flow_y_rads = flow_y_dpi / (pixels_per_radian_v * dt)

                            logger.debug(f"{logging_prefix_str} Frame:{frame_count} "
                                         f"flow_x={flow_x_dpi:.4f}, flow_y={flow_y_dpi:.4f} "
                                         f"flow_rate_x={flow_x_rads:.4f} rad/s, flow_rate_y={flow_y_rads:.4f} rad/s dt={dt:.4f}s")

                            # Send OPTICAL_FLOW message
                            mavlink_start_time = time.time()
                            send_result = mavlink_interface.send_optical_flow_msg(
                                sysid=target_system_id,   # system ID of the target vehicle
                                flow_x=int(flow_x_dpi),   # flow_x in pixels
                                flow_y=int(flow_y_dpi),   # flow_y in pixels
                                flow_comp_m_x=0.0,        # flow_comp_m_x (gimbaled camera so always zero)
                                flow_comp_m_y=0.0,        # flow_comp_m_y (gimbaled camera so always zero)
                                quality=255,              # quality (0 to 255, 255 means good quality)
                                ground_distance=-1,       # ground distance is unknown
                                flow_rate_x=flow_x_rads,  # flow rate in x direction (rad/s)
                                flow_rate_y=flow_y_rads   # flow rate in y direction (rad/s)
                            )
                            mavlink_send_time = time.time() - mavlink_start_time

                            if send_result["success"]:
                                sent_count += 1
                            else:
                                logger.error(f"{logging_prefix_str} Failed to send OPTICAL_FLOW: {send_result['message']}")
                        else:
                            logger.warning(f"{logging_prefix_str} Invalid dt value: {dt:.4f}s, not sending OPTICAL_FLOW")

                        # record last send time
                        last_send_time = time.time()
                    else:
                        logger.debug(f"{logging_prefix_str} optical flow calculation failed: {opticalflow_result.get('message', 'unknown error')}")
                else:
                    # log that we are waiting for gimbal to face downwards
                    logger.debug(f"{logging_prefix_str} waiting for gimbal to face downwards")

                # Calculate total loop time and log timing details
                loop_total_time = time.time() - loop_start_time

                # Log detailed timing every 10 frames or if any stage takes unusually long
                if frame_count % 10 == 0 or loop_total_time > 0.05:
                    logger.debug(f"{logging_prefix_str} TIMING Frame:{frame_count} "
                                 f"Total:{loop_total_time*1000:.1f}ms "
                                 f"FrameCapture:{frame_capture_time*1000:.1f}ms "
                                 f"GimbalCheck:{gimbal_check_time*1000:.1f}ms "
                                 f"OpticalFlow:{optflow_calc_time*1000:.1f}ms "
                                 f"MAVLinkSend:{mavlink_send_time*1000:.1f}ms")

                # log every 5 seconds
                current_time = time.time()
                if current_time - last_log_time > 5:
                    update_rate_hz = frame_count / (current_time - last_log_time)
                    avg_loop_time = (current_time - last_log_time) / frame_count * 1000  # ms
                    logger.info(f"{logging_prefix_str} rate:{update_rate_hz:.1f}hz frames:{frame_count} MsgsSent:{sent_count} "
                                f"AvgLoopTime:{avg_loop_time:.1f}ms")
                    last_log_time = current_time
                    frame_count = 0
                    sent_count = 0

                # sleep to reduce CPU load
                # long sleep if gimbal is not vertical
                sleep_time = 0.01
                if current_time - last_send_time > 10:
                    sleep_time = 0.8
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"{logging_prefix_str} loop error {str(e)}")
                await asyncio.sleep(1)  # Wait 1 second before retrying

    except Exception as e:
        logger.error(f"{logging_prefix_str} error {str(e)}")
        mavlink_interface.send_statustext_msg(target_system_id, "OpticalFlow: error")
    finally:
        # Clean up video capture when stopping
        image_capture.cleanup_video_capture()
        opticalflow_running = False
        mavlink_interface.send_statustext_msg(target_system_id, "OpticalFlow: stopped")
        logger.info(f"{logging_prefix_str} stopped")


# Test RTSP connection using OpenCV with FFMPEG backend
# Called from index.html's Test button
def test_rtsp_connection(rtsp_url: str, camera_type: str) -> Dict[str, Any]:
    """
    Test RTSP connection and capture a frame with optical flow calculation.
    Returns connection status and basic stream information.
    """

    try:
        # Capture single frame from RTSP stream
        frame_result = image_capture.capture_frame_from_stream(rtsp_url)

        if not frame_result["success"]:
            return {
                "success": False,
                "message": f"RTSP connection failed: {frame_result['message']}",
                "error": frame_result.get("error", "Frame capture failed")
            }

        # Get frame data
        frame = frame_result["frame"]
        width = frame_result["width"]
        height = frame_result["height"]

        # Test optical flow calculation
        opticalflow_result = optflow_lkt.get_optical_flow(frame, time.time(), True)  # Include augmented image

        # Encode frame as base64 (use augmented image if available)
        if opticalflow_result.get("success") and opticalflow_result.get("image_base64"):
            image_base64 = opticalflow_result["image_base64"]
        else:
            # Fall back to original frame
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "success": True,
            "message": f"RTSP connection successful ({width}x{height}). Method: {rtsp_url}",
            "connection_method": rtsp_url,
            "resolution": f"{width}x{height}",
            "image_base64": image_base64,
            "optical_flow": opticalflow_result
        }

    except Exception as e:
        logger.exception(f"test_rtsp_connection: exception {str(e)}")
        return {
            "success": False,
            "message": f"Error testing RTSP connection: {str(e)}. Method: {rtsp_url}",
            "error": str(e)
        }


# helper function to calculate the vertical FOV based on the horizontal FOV, image width, and height (in pixels)
def calculate_vertical_fov(hfov_deg: float, width: int, height: int) -> float:
    """Calculate vertical FOV based on horizontal FOV, image width, and height
       tan(vfov/2) = tan(hfov/2) * (height/width)
    """

    # logging prefix for all messages from this function
    logging_prefix_str = "calculate_vertical_fov:"

    # Validate inputs to prevent mathematical errors
    if width <= 0:
        logger.error(f"{logging_prefix_str} invalid image width: {width}")
        return 0.0

    if height <= 0:
        logger.error(f"{logging_prefix_str} invalid image height: {height}")
        return 0.0

    if hfov_deg <= 0 or hfov_deg >= 180:
        logger.error(f"{logging_prefix_str} invalid horizontal FOV: {hfov_deg} (must be between 0 and 180)")
        return 0.0

    try:
        # Convert horizontal FOV from degrees to radians
        hfov_rad = radians(hfov_deg)

        # Calculate aspect ratio
        aspect_ratio = height / width

        # Use trigonometric relationship to calculate vertical FOV
        vfov_rad = 2 * atan(tan(hfov_rad / 2) * aspect_ratio)

        # Convert back to degrees
        vfov_deg = degrees(vfov_rad)

        # Sanity check result
        if vfov_deg <= 0 or vfov_deg >= 180:
            logger.error(f"{logging_prefix_str} calculated invalid VFOV: {vfov_deg}")
            return 0.0

        return vfov_deg
    except (ValueError, OverflowError) as e:
        logger.error(f"{logging_prefix_str} mathematical error calculating VFOV: {e}")
        return 0.0


# calculate the angle in radians between two quaternions
def angle_between_quaternions(q1, q2):
    # Ensure both quaternions are unit length
    dot = abs(q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3])
    dot = min(1.0, max(-1.0, dot))  # Clamp for acos
    return 2 * math.acos(dot)  # in radians


# Optical Flow API Endpoints

# Get the list of available camera configs (RTSP and FOV)
@app.get("/opticalflow/camera-configs")
async def get_camera_configs() -> Dict[str, Any]:
    """Return the list of available camera configs (RTSP and FOV)"""
    logger.debug("Getting camera configs")

    try:
        settings_dict = settings.get_settings()
        cameras = settings_dict.get('cameras', {})
        return {"success": True, "camera_configs": cameras}
    except Exception as e:
        logger.error(f"Error getting camera configs: {str(e)}")
        return {"success": False, "message": str(e)}


# Load opticalflow settings
@app.post("/opticalflow/get-settings")
async def get_opticalflow_settings() -> Dict[str, Any]:
    """Get saved camera settings"""
    logger.debug("Getting opticalflow settings")

    try:
        # Get the last used camera settings
        last_used = settings.get_last_used()

        # Get RTSP URLs and FOV values for all camera types
        cameras = {}
        for camera_type in ["siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb"]:
            rtsp_url = settings.get_camera_rtsp(camera_type)
            horizontal_fov = settings.get_camera_horizontal_fov(camera_type)
            cameras[camera_type] = {
                "rtsp": rtsp_url,
                "horizontal_fov": horizontal_fov
            }

        # Get MAVLink settings
        mavlink_settings = {
            "flight_controller_sysid": settings.get_mavlink_sysid()
        }

        # Get gimbal settings
        gimbal_settings = {
            "use_gimbal_attitude": settings.get_gimbal_attitude_settings()
        }

        return {
            "success": True,
            "last_used": last_used,
            "cameras": cameras,
            "mavlink": mavlink_settings,
            "gimbal_attitude": gimbal_settings
        }
    except Exception as e:
        logger.exception(f"Error getting opticalflow settings: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}"}


# Save opticalflow settings
@app.post("/opticalflow/save-settings")
async def save_opticalflow_settings(
    type: str = Query(...),
    rtsp: str = Query(...),
    fov: float = Query(...),
    flight_controller_sysid: int = Query(...),  # Keep this for HTML compatibility
    use_gimbal_attitude: bool = Query(True)     # Default to True
) -> Dict[str, Any]:
    """Save camera settings and other opticalflow settings to persistent storage (using query parameters)"""
    # Map flight_controller_sysid to sysid for internal use
    sysid = flight_controller_sysid
    logger.info(f"Saving opticalflow settings: camera_type={type}, rtsp_url={rtsp}, fov={fov}, "
                f"sysid={sysid}, use_gimbal_attitude={use_gimbal_attitude}")

    # Save camera settings
    camera_success = settings.update_camera_settings(type, rtsp, fov)

    # Save MAVLink settings
    mavlink_success = settings.update_mavlink_sysid(sysid)

    # Save gimbal attitude settings
    gimbal_success = settings.update_gimbal_attitude_settings(use_gimbal_attitude)

    if camera_success and mavlink_success and gimbal_success:
        return {"success": True, "message": f"Settings saved for {type}"}
    else:
        return {"success": False, "message": "Failed to save some settings"}


# Get opticalflow enabled state
@app.get("/opticalflow/get-enabled-state")
async def get_opticalflow_enabled_state() -> Dict[str, Any]:
    """Get saved opticalflow enabled state (supports both GET and POST)"""
    logger.debug("Getting opticalflow enabled state")

    try:
        enabled = settings.get_opticalflow_enabled()
        return {
            "success": True,
            "enabled": enabled
        }
    except Exception as e:
        logger.exception(f"Error getting opticalflow enabled state: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}", "enabled": False}


# Save opticalflow enabled state
@app.post("/opticalflow/save-enabled-state")
async def save_opticalflow_enabled_state(enabled: bool = Query(...)) -> Dict[str, Any]:
    """Save opticalflow enabled state to persistent storage (using query parameter)"""
    logger.info(f"Optical flow enabled state: {enabled}")
    success = settings.update_opticalflow_enabled(enabled)

    if success:
        return {"success": True, "message": f"Enabled state saved: {enabled}"}
    else:
        return {"success": False, "message": "Failed to save enabled state"}


# Test image retrieval from the RTSP stream and optical flow calculation
@app.post("/opticalflow/test")
async def test_opticalflow(type: str = Query(...), rtsp: str = Query(...)) -> Dict[str, Any]:
    """Test opticalflow functionality with RTSP connection"""
    logger.info(f"Testing with camera_type={type}, rtsp={rtsp}")

    try:
        # Run the RTSP connection test in a thread to avoid blocking
        def run_test():
            return test_rtsp_connection(rtsp, type)

        # Run the test in an executor to avoid blocking the async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)  # 60 second timeout should be sufficient

        if result["success"]:
            logger.info(f"RTSP test successful for {type}: {result['message']}")
            # Add camera type to the response
            result["camera_type"] = type
            result["rtsp_url"] = rtsp
        else:
            logger.warning(f"RTSP test failed for {type}: {result['message']}")

        return result

    except concurrent.futures.TimeoutError:
        logger.error(f"RTSP test timed out for {type} camera")
        return {
            "success": False,
            "message": "Test timed out - unable to connect to camera within 60 seconds",
            "error": "Connection timeout"
        }
    except Exception as e:
        logger.exception(f"Error during opticalflow test: {str(e)}")
        return {"success": False, "message": f"Test failed: {str(e)}"}


# Get opticalflow running status
@app.get("/opticalflow/status")
async def get_opticalflow_status() -> Dict[str, Any]:
    """Get opticalflow running status"""
    logger.debug("Getting opticalflow status")

    try:
        return {
            "success": True,
            "running": opticalflow_running,
            "message": "Running" if opticalflow_running else "Stopped"
        }
    except Exception as e:
        logger.exception(f"Error getting opticalflow status: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}", "running": False}


# Start opticalflow (this is called by the frontend's "Run" button)
@app.post("/opticalflow/start")
async def start_opticalflow(type: str = Query(...), rtsp: str = Query(...)) -> Dict[str, Any]:
    """Start opticalflow"""
    logger.info(f"Start opticalflow request received for type={type}, rtsp={rtsp}")

    try:
        if opticalflow_running:
            return {"success": False, "message": "Optical flow is already running"}

        # Start the opticalflow process
        asyncio.create_task(start_opticalflow_internal(type, rtsp))

        # Wait a few seconds to catch immediate failures
        await asyncio.sleep(2)

        # Check if it's actually running now
        if opticalflow_running:
            return {
                "success": True,
                "message": f"Optical flow started successfully with {type} camera"
            }
        else:
            return {
                "success": False,
                "message": "Optical flow failed to start (check logs for details)"
            }

    except Exception as e:
        logger.exception(f"Error starting opticalflow: {str(e)}")
        return {"success": False, "message": f"Failed to start: {str(e)}"}


# Stop opticalflow (this is called by the frontend's "Stop" button)
@app.post("/opticalflow/stop")
async def stop_opticalflow() -> Dict[str, Any]:
    """Stop opticalflow"""
    global opticalflow_running

    logger.info("Stop opticalflow request received")

    try:
        # Stop the opticalflow process
        opticalflow_running = False

        # Clean up video capture when manually stopping
        image_capture.cleanup_video_capture()

        return {
            "success": True,
            "message": "Optical flow stopped successfully"
        }
    except Exception as e:
        logger.exception(f"Error stopping opticalflow: {str(e)}")
        return {"success": False, "message": f"Failed to stop: {str(e)}"}


# Initialize auto-restart task
@app.on_event("startup")
async def on_startup():
    """Application startup event handler"""
    await startup_auto_restart()


# Mount static files AFTER defining API routes
# Use absolute path to handle Docker container environment
static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Set up logging for the app
log_dir = Path('./logs')  # Use local logs directory instead of /app/logs
log_dir.mkdir(parents=True, exist_ok=True)
fh = logging.handlers.RotatingFileHandler(log_dir / 'lumber.log', maxBytes=2**16, backupCount=1)
logger.addHandler(fh)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
