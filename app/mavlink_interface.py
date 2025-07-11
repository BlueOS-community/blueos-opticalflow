#!/usr/bin/env python3

"""
Optical Flow MAVLink Message Module

This module handles sending OPTICAL_FLOW and STATUSTEXT MAVLink messages to the vehicle
via BlueOS MAV2Rest API interface.
"""

import time
import logging
import json
from typing import Dict, Any, Optional
import urllib.request

# Get logger
logger = logging.getLogger("opticalflow")

# MAV2Rest endpoint
MAV2REST_ENDPOINT = "http://host.docker.internal:6040"

# MAVLink component ID
MAV_COMP_ID_ONBOARD_COMPUTER = 191  # Component ID for onboard computer systems

# COMMAND_LONG message template for SET_MESSAGE_INTERVAL
COMMAND_LONG_SET_MESSAGE_INTERVAL_TEMPLATE = """{{
  "header": {{
    "system_id": {sysid},
    "component_id": {component_id},
    "sequence": 0
  }},
  "message": {{
    "type": "COMMAND_LONG",
    "target_system": {target_system},
    "target_component": {target_component},
    "command": {{
      "type": "MAV_CMD_SET_MESSAGE_INTERVAL"
    }},
    "confirmation": 0,
    "param1": {message_id},
    "param2": {interval_us},
    "param3": {param3},
    "param4": {param4},
    "param5": {param5},
    "param6": {param6},
    "param7": {response_target}
  }}
}}"""

# OPTICAL_FLOW message template
OPTICAL_FLOW_TEMPLATE = """{{
  "header": {{
    "system_id": {sysid},
    "component_id": {component_id},
    "sequence": 0
  }},
  "message": {{
    "type": "OPTICAL_FLOW",
    "time_usec": {time_usec},
    "sensor_id": {sensor_id},
    "flow_x": {flow_x},
    "flow_y": {flow_y},
    "flow_comp_m_x": {flow_comp_m_x},
    "flow_comp_m_y": {flow_comp_m_y},
    "quality": {quality},
    "ground_distance": {ground_distance},
    "flow_rate_x": {flow_rate_x},
    "flow_rate_y": {flow_rate_y}
  }}
}}"""

# STATUSTEXT message template
STATUSTEXT_TEMPLATE = """{{
  "header": {{
    "system_id": {sysid},
    "component_id": {component_id},
    "sequence": 0
  }},
  "message": {{
    "type": "STATUSTEXT",
    "severity": {{
      "type": "{severity}"
    }},
    "text": "{text}",
    "id": {id},
    "chunk_seq": {chunk_seq}
  }}
}}"""


# send mavlink message using MAV2Rest
def post_to_mav2rest(url: str, data: str) -> Optional[str]:
    """
    Sends a POST request to MAV2Rest with JSON data
    Returns response text if successful, None otherwise
    """
    try:
        jsondata = data.encode("ascii")  # data should be bytes
        req = urllib.request.Request(url, jsondata)
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode()
    except Exception as error:
        logger.error(f"post_to_mav2rest: error : {url}: {error}")
        return None


# Low level function to send OPTICAL_FLOW MAVLink message
def send_optical_flow_msg(sysid: int,
                          flow_x: int,
                          flow_y: int,
                          flow_comp_m_x: float,
                          flow_comp_m_y: float,
                          quality: int,
                          ground_distance: float,
                          flow_rate_x: float,
                          flow_rate_y: float) -> Dict[str, Any]:
    """
    Send OPTICAL_FLOW MAVLink message

    Args:
        sysid: System ID to send message (normally 1)
        flow_x: Flow in x-sensor direction in dpix
        flow_y: Flow in y-sensor direction in dpiy
        flow_comp_m_x: Flow in x-axis in ground plane in meters/second
        flow_comp_m_y: Flow in y-axis in ground plane in meters/second
        quality: Optical flow quality (0=bad, 255=maximum quality)
        ground_distance: Ground distance in meters, negative if unknown
        flow_rate_x: Flow rate about X axis in radians/second
        flow_rate_y: Flow rate about Y axis in radians/second

    Returns:
        Dictionary with send results
    """

    # logging prefix for all messages from this function
    logging_prefix_str = "send_optical_flow_msg:"

    try:
        # Get current time in microseconds since UNIX epoch
        time_usec = int(time.time() * 1000000)

        # Format the OPTICAL_FLOW message
        optical_flow_data = OPTICAL_FLOW_TEMPLATE.format(
            sysid=sysid,
            component_id=MAV_COMP_ID_ONBOARD_COMPUTER,
            time_usec=time_usec,
            sensor_id=0,
            flow_x=int(flow_x),  # Flow in x-sensor direction in dpix
            flow_y=int(flow_y),  # Flow in y-sensor direction in dpiy
            flow_comp_m_x=flow_comp_m_x,  # Flow in x-sensor direction in m/s, angular-speed compensated
            flow_comp_m_y=flow_comp_m_y,  # Flow in y-sensor direction in m/s, angular-speed compensated
            quality=quality,  # Optical flow quality / confidence. 0: bad, 255: maximum quality
            ground_distance=ground_distance,  # Ground distance. Positive value: distance known. Negative value: Unknown distance
            flow_rate_x=flow_rate_x,  # Flow rate about X axis in radians/second
            flow_rate_y=flow_rate_y   # Flow rate about Y axis in radians/second
        )

        # Send message via MAV2Rest
        url = f"{MAV2REST_ENDPOINT}/mavlink"
        response = post_to_mav2rest(url, optical_flow_data)

        if response is not None:
            logger.debug(f"{logging_prefix_str} OPTICAL_FLOW sent with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER} flow_rate_x={flow_rate_x:.4f} rad/s, flow_rate_y={flow_rate_y:.4f} rad/s")
            return {
                "success": True,
                "message": f"OPTICAL_FLOW message sent successfully with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}",
                "time_usec": time_usec,
                "flow_rate_x": flow_rate_x,
                "flow_rate_y": flow_rate_y,
                "quality": quality,
                "ground_distance": ground_distance,
                "sysid": sysid,
                "response": response
            }
        else:
            logger.error(f"{logging_prefix_str} failed to send OPTICAL_FLOW")
            return {
                "success": False,
                "message": "MAV2Rest returned no response",
                "network_error": True
            }

    except Exception as e:
        logger.error(f"{logging_prefix_str} unexpected error {str(e)}")
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "unexpected_error": True
        }


# Low level function to send STATUSTEXT MAVLink message
def send_statustext_msg(sysid: int,
                        text: str,
                        severity: str = "MAV_SEVERITY_INFO",
                        message_id: int = 0,
                        chunk_seq: int = 0) -> Dict[str, Any]:
    """
    Send STATUSTEXT MAVLink message

    Args:
        sysid: System ID to send message (normally 1)
        text: Status text message (max 50 characters)
        severity: Message severity level (MAV_SEVERITY_EMERGENCY, MAV_SEVERITY_ALERT,
                 MAV_SEVERITY_CRITICAL, MAV_SEVERITY_ERROR, MAV_SEVERITY_WARNING,
                 MAV_SEVERITY_NOTICE, MAV_SEVERITY_INFO, MAV_SEVERITY_DEBUG)
        message_id: Unique (or wrap around) id for this message (0 for auto)
        chunk_seq: Allows the safe construction of larger messages from chunks

    Returns:
        Dictionary with send results
    """

    # logging prefix for all messages from this function
    logging_prefix_str = "send_statustext_msg:"

    try:
        # Truncate text to 50 characters (MAVLink STATUSTEXT limit)
        if len(text) > 50:
            text = text[:50]
            logger.warning(f"{logging_prefix_str} text truncated to 50 characters")

        # Format the STATUSTEXT message
        statustext_data = STATUSTEXT_TEMPLATE.format(
            sysid=sysid,
            component_id=MAV_COMP_ID_ONBOARD_COMPUTER,
            severity=severity,
            text=text,
            id=message_id,
            chunk_seq=chunk_seq
        )

        # Send message via MAV2Rest
        url = f"{MAV2REST_ENDPOINT}/mavlink"
        response = post_to_mav2rest(url, statustext_data)

        if response is not None:
            logger.debug(f"{logging_prefix_str} STATUSTEXT sent with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}: '{text}'")
            return {
                "success": True,
                "message": f"STATUSTEXT message sent successfully with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}",
                "text": text,
                "severity": severity,
                "sysid": sysid,
                "response": response
            }
        else:
            logger.error(f"{logging_prefix_str} failed to send STATUSTEXT")
            return {
                "success": False,
                "message": "MAV2Rest returned no response",
                "network_error": True
            }

    except Exception as e:
        logger.error(f"{logging_prefix_str} unexpected error {str(e)}")
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "unexpected_error": True
        }


# Retrieve the latest GIMBAL_DEVICE_ATTITUDE_STATUS message via MAV2Rest
def get_gimbal_attitude(sysid: int) -> Dict[str, Any]:
    """
    Retrieve the latest GIMBAL_DEVICE_ATTITUDE_STATUS message via MAV2Rest

    Args:
        sysid: System ID to query gimbal attitude from

    Returns:
        Dictionary with gimbal attitude data or error information
    """

    # logging prefix for all messages from this function
    logging_prefix_str = "get_gimbal_attitude:"

    try:
        # Request the latest GIMBAL_DEVICE_ATTITUDE_STATUS message from the autopilot
        compid = 1  # autopilot component ID
        url = f"{MAV2REST_ENDPOINT}/mavlink/vehicles/{sysid}/components/{compid}/messages/GIMBAL_DEVICE_ATTITUDE_STATUS"
        req = urllib.request.Request(url)
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=5) as response:
            if response.getcode() == 200:
                response_data = response.read().decode()

                # Parse the response (MAV2Rest returns JSON)
                data = json.loads(response_data)

                # Extract attitude information from the message
                if "message" in data:
                    msg = data["message"]

                    # Extract quaternion components
                    q = msg.get("q", [1.0, 0.0, 0.0, 0.0])

                    # log attitude as quaternion
                    logger.debug(f"{logging_prefix_str} q0:{q[0]:.4f}, q1:{q[1]:.4f}, q2:{q[2]:.5f}, q3:{q[3]:.4f}")

                    return {
                        "success": True,
                        "message": f"Gimbal attitude retrieved successfully",
                        "quaternion": {
                            "w": q[0],
                            "x": q[1],
                            "y": q[2],
                            "z": q[3]
                        }
                    }
                else:
                    logger.warning(f"{logging_prefix_str} could not parse GIMBAL_DEVICE_ATTITUDE_STATUS message")
                    return {
                        "success": False,
                        "message": "Invalid gimbal attitude message format",
                        "raw_response": response_data
                    }
            else:
                logger.warning(f"{logging_prefix_str} HTTP error {response.getcode()} retrieving gimbal attitude")
                return {
                    "success": False,
                    "message": f"HTTP error {response.getcode()}",
                    "http_error": True
                }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.warning(f"{logging_prefix_str} GIMBAL_DEVICE_ATTITUDE_STATUS not found")
            return {
                "success": False,
                "message": "Gimbal not found or not publishing attitude data",
                "error": "Gimbal not available"
            }
        else:
            logger.error(f"{logging_prefix_str} could not retrieve GIMBAL_DEVICE_ATTITUDE_STATUS {e.code} - {e.reason}")
            return {
                "success": False,
                "message": f"HTTP error {e.code}: {e.reason}",
                "http_error": True
            }
    except urllib.error.URLError as e:
        logger.error(f"Network error retrieving gimbal attitude: {e.reason}")
        return {
            "success": False,
            "message": f"Network error: {e.reason}",
            "network_error": True
        }
    except Exception as e:
        logger.error(f"{logging_prefix_str} could not retrieve GIMBAL_DEVICE_ATTITUDE_STATUS: {str(e)}")
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "unexpected_error": True
        }


# request GIMBAL_DEVICE_ATTITUDE_STATUS messages at specified rate
def request_gimbal_attitude_status(sysid: int, interval_hz: float) -> Dict[str, Any]:
    """
    Request GIMBAL_DEVICE_ATTITUDE_STATUS messages at specified rate

    Args:
        sysid: System ID to send message to
        interval_hz: Frequency in Hz (1.0 = 1Hz, 0 = disable)

    Returns:
        Dictionary with send results
    """

    logger.debug(f"request_gimbal_attitude_status: requesting GIMBAL_DEVICE_ATTITUDE_STATUS at {interval_hz}Hz")

    return send_set_message_interval(
        sysid=sysid,
        message_id=285,         # GIMBAL_DEVICE_ATTITUDE_STATUS
        interval_hz=interval_hz
    )


# send SET_MESSAGE_INTERVAL command
def send_set_message_interval(sysid: int,  # target system id
                              message_id: int,  # MAVlink message id
                              interval_hz: float) -> Dict[str, Any]:
    """
    Send COMMAND_LONG with MAV_CMD_SET_MESSAGE_INTERVAL to request specific message at given rate

    Args:
        sysid: System ID to send message to (e.g 1 for autopilot)
        message_id: MAVLink message ID to request (e.g 285 for GIMBAL_DEVICE_ATTITUDE_STATUS)
        interval_hz: Frequency in Hz (-1 = disable, 0 = request default rate, 1.0 = 1Hz)

    Returns:
        Dictionary with send results
    """
    logging_prefix_str = "set_message_interval"

    try:
        # Convert frequency to interval in microseconds
        if interval_hz < 0:
            interval_us = -1  # Disable the message
            logger.info(f"{logging_prefix_str}: disabling message {message_id}")
        elif interval_hz == 0:
            interval_us = 0  # Request default rate (0 = default)
            logger.info(f"{logging_prefix_str}: default rate for {message_id}")
        else:
            interval_us = int(1000000 / interval_hz)  # Convert Hz to microseconds
            logger.info(f"{logging_prefix_str}: requesting message ID {message_id} at {interval_hz}Hz ({interval_us}µs interval)")

        # Format the COMMAND_LONG message with SET_MESSAGE_INTERVAL command
        target_compid = 1  # autopilot component ID
        command_data = COMMAND_LONG_SET_MESSAGE_INTERVAL_TEMPLATE.format(
            sysid=sysid,
            component_id=MAV_COMP_ID_ONBOARD_COMPUTER,
            target_system=sysid,
            target_component=target_compid,  # autopilot component ID
            message_id=message_id,
            interval_us=interval_us,
            param3=0.0,        # Unused
            param4=0.0,        # Unused
            param5=0.0,        # Unused
            param6=0.0,        # Unused
            response_target=1  # requestor is target address of message stream
        )

        # Send message via MAV2Rest
        url = f"{MAV2REST_ENDPOINT}/mavlink"
        response = post_to_mav2rest(url, command_data)

        if response is not None:
            logger.info(f"{logging_prefix_str}: sent SET_MESSAGE_INTERVAL to sysid:{sysid} compid:{target_compid} msg_id:{message_id}, interval={interval_hz}Hz)")
            return {
                "success": True,
                "message": f"SET_MESSAGE_INTERVAL sent to sysid:{sysid} compid:{target_compid} msg_id:{message_id}, interval={interval_hz}Hz)",
                "message_id": message_id,
                "interval_hz": interval_hz,
                "interval_us": interval_us,
                "target_component": target_compid,
                "response": response
            }
        else:
            logger.error(f"{logging_prefix_str}: failed to send SET_MESSAGE_INTERVAL to sysid:{sysid} compid:{target_compid} msg_id:{message_id}, interval={interval_hz}Hz)")
            return {
                "success": False,
                "message": "MAV2Rest returned no response",
                "network_error": True
            }

    except Exception as e:
        logger.error(f"{logging_prefix_str}: failed to send SET_MESSAGE_INTERVAL: {str(e)}")
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "unexpected_error": True
        }
