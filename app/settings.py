#!/usr/bin/env python3

# Precision Landing Settings Management

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger("opticalflow.settings")

# Settings file path - stored in the extension's persistent storage directory
SETTINGS_FILE = Path('/app/settings/opticalflow-settings.json')

# Default settings
DEFAULT_SETTINGS = {
    'cameras': {
        'siyi-a8': {
            'rtsp': 'rtsp://192.168.144.25:8554/main.264',
            'horizontal_fov': 81
        },
        'siyi-zr10': {
            'rtsp': 'rtsp://192.168.144.25:8554/main.264',
            'horizontal_fov': 62
        },
        'siyi-zt6-ir': {
            'rtsp': 'rtsp://192.168.144.25:8554/video1',
            'horizontal_fov': 32
        },
        'siyi-zt6-rgb': {
            'rtsp': 'rtsp://192.168.144.25:8554/video2',
            'horizontal_fov': 85
        },
        'xfrobot-z1-mini': {
            'rtsp': 'rtsp://192.168.144.108',
            'horizontal_fov': 54.7
        }
    },
    'last_used': {
        'camera_type': 'siyi-a8',
        'rtsp': 'rtsp://192.168.144.25:8554/main.264',
        'horizontal_fov': 81
    },
    'opticalflow': {
        'enabled': False
    },
    'mavlink': {
        'sysid': 1
    },
    'gimbal': {
        'use_gimbal_attitude': True
    }
}


# get the dictionary of settings from the settings file
def get_settings():
    """
    Load settings from the settings file.
    Creates default settings file if it doesn't exist.
    Merges with defaults to ensure new camera types are available.

    Returns:
        dict: The settings dictionary
    """
    try:
        if not SETTINGS_FILE.exists():
            logger.info(f"Settings file not found, creating default at {SETTINGS_FILE}")
            save_settings(DEFAULT_SETTINGS)
            return DEFAULT_SETTINGS

        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)

            # merge with defaults to ensure new camera types are available
            if 'cameras' not in settings:
                settings['cameras'] = {}

            # add any missing cameras from defaults
            for camera_type, camera_config in DEFAULT_SETTINGS['cameras'].items():
                if camera_type not in settings['cameras']:
                    settings['cameras'][camera_type] = camera_config.copy()
                    logger.info(f"Added new camera type {camera_type} to settings")

            return settings
    except Exception as e:
        logger.error(f"Error loading settings, using defaults: {e}")
        # Try to save default settings for next time
        try:
            save_settings(DEFAULT_SETTINGS)
        except Exception:
            logger.exception("Failed to save default settings")

        return DEFAULT_SETTINGS


# save settings to the settings file
def save_settings(settings):
    """
    Save settings to the settings file

    Args:
        settings (dict): Settings dictionary to save
    """
    try:
        # Ensure parent directory exists
        os.makedirs(SETTINGS_FILE.parent, exist_ok=True)

        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


# update the camera RTSP URL and FOV in the settings file
def update_camera_settings(camera_type, rtsp, horizontal_fov):
    """
    Update the RTSP URL and horizontal FOV for a specific camera type

    Args:
        camera_type (str): The camera type ("siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb")
        rtsp (str): The RTSP URL
        horizontal_fov (float): The horizontal field of view in degrees

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Update camera settings
        if camera_type not in settings['cameras']:
            settings['cameras'][camera_type] = {}

        settings['cameras'][camera_type]['rtsp'] = rtsp
        settings['cameras'][camera_type]['horizontal_fov'] = horizontal_fov

        # Update last used settings
        last_used = {
            'camera_type': camera_type,
            'rtsp': rtsp,
            'horizontal_fov': horizontal_fov
        }
        settings['last_used'] = last_used

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating camera settings: {e}")
        return False


# get the latest RTSP URL for a specific camera type
def get_camera_rtsp(camera_type):
    """
    Get the saved RTSP URL for a camera type

    Args:
        camera_type (str): The camera type ("siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb")

    Returns:
        str: The saved RTSP URL or default if not found
    """
    settings = get_settings()

    # Check if camera type exists in settings
    if camera_type in settings['cameras'] and 'rtsp' in settings['cameras'][camera_type]:
        return settings['cameras'][camera_type]['rtsp']

    # Return default RTSP URL if not found
    if camera_type in DEFAULT_SETTINGS['cameras']:
        return DEFAULT_SETTINGS['cameras'][camera_type]['rtsp']
    else:
        # Fallback to siyi-a8 if camera type not found
        return DEFAULT_SETTINGS['cameras']['siyi-a8']['rtsp']


# get the horizontal FOV for a specific camera type
def get_camera_horizontal_fov(camera_type):
    """
    Get the saved horizontal FOV for a camera type

    Args:
        camera_type (str): The camera type ("siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb")

    Returns:
        float: The saved horizontal FOV in degrees or default if not found
    """
    settings = get_settings()

    # Check if camera type exists in settings
    if camera_type in settings['cameras'] and 'horizontal_fov' in settings['cameras'][camera_type]:
        return settings['cameras'][camera_type]['horizontal_fov']

    # Return default FOV if not found
    if camera_type in DEFAULT_SETTINGS['cameras']:
        return DEFAULT_SETTINGS['cameras'][camera_type]['horizontal_fov']
    else:
        # Fallback to siyi-a8 if camera type not found
        return DEFAULT_SETTINGS['cameras']['siyi-a8']['horizontal_fov']


# get the last used camera type and RTSP URL
def get_last_used():
    """
    Get the last used camera type and RTSP URL

    Returns:
        dict: Dictionary with camera_type and rtsp
    """
    settings = get_settings()
    return settings.get('last_used', DEFAULT_SETTINGS['last_used'])


# get the opticalflow enabled state
def get_opticalflow_enabled():
    """
    Get the opticalflow enabled state

    Returns:
        bool: True if opticalflow is enabled, False otherwise
    """
    try:
        settings = get_settings()

        # Check if opticalflow section exists
        if 'opticalflow' in settings and 'enabled' in settings['opticalflow']:
            return settings['opticalflow']['enabled']

        # Return default if not found
        return DEFAULT_SETTINGS['opticalflow']['enabled']
    except Exception as e:
        logger.error(f"Error getting opticalflow enabled state: {e}")
        return False


# update the opticalflow enabled state
def update_opticalflow_enabled(enabled):
    """
    Update the opticalflow enabled state

    Args:
        enabled (bool): Whether opticalflow is enabled

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Ensure opticalflow section exists
        if 'opticalflow' not in settings:
            settings['opticalflow'] = {}

        settings['opticalflow']['enabled'] = enabled

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating opticalflow enabled state: {e}")
        return False


# get MAVLink sysid
def get_mavlink_sysid():
    """
    Get the MAVLink system ID setting

    Returns:
        int: The system ID (default: 1)
    """
    settings = get_settings()
    return settings.get('mavlink', {}).get('sysid', DEFAULT_SETTINGS['mavlink']['sysid'])


# update MAVLink sysid
def update_mavlink_sysid(sysid):
    """
    Update MAVLink sysid

    Args:
        sysid (int): The system ID

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Ensure mavlink section exists
        if 'mavlink' not in settings:
            settings['mavlink'] = {}

        settings['mavlink']['sysid'] = sysid

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating MAVLink settings: {e}")
        return False


# get gimbal attitude setting
def get_gimbal_attitude_settings():
    """
    Get the gimbal attitude usage setting

    Returns:
        bool: True if gimbal attitude should be used, False otherwise
    """
    settings = get_settings()
    return settings.get('gimbal', {}).get('use_gimbal_attitude', DEFAULT_SETTINGS['gimbal']['use_gimbal_attitude'])


# update gimbal attitude setting
def update_gimbal_attitude_settings(use_gimbal_attitude):
    """
    Update gimbal attitude usage setting

    Args:
        use_gimbal_attitude (bool): Whether to use gimbal attitude for targeting

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Ensure gimbal section exists
        if 'gimbal' not in settings:
            settings['gimbal'] = {}

        settings['gimbal']['use_gimbal_attitude'] = use_gimbal_attitude

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating gimbal attitude settings: {e}")
        return False
