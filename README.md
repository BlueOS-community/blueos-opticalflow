# Optical Flow

BlueOS Extension to support optical flow using an ethernet enabled camera gimbal

## Usage

Users should select the Camera Type and update the RTSP URL if different from the default

Push the "Test" button to a snapshot of the live video and optical flow values

Push the "Run" button to enable optical flow including sending MAVLink messages to the vehicle.  This setting is persistent

## Developer Information

To build and publish for Ubuntu, RPI3, RPI4, RPI5

- Open docker desktop (required only on Windows WSL2 machines)
- docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64/v8 . -t YOURDOCKERHUBUSER/YOURDOCKERHUBREPO:latest --output type=registry
- login to https://hub.docker.com/repositories/ and confirm the image has appeared

To manually install the extension in BlueOS

- Start BlueOS on RPI, open Chrome browser and connect to BlueOS (e.g. via WifiAP use http://blueos-hotspot.local/, if on same network use http://blueos-avahi.local/)
- Open BlueOS Extensions tab, select Installed
  - Push "+" button on the bottom right
  - Under "Create Extension" fill in these fields
    - Extension Identifier: YOURDOCKERHUBUSER.YOURDOCKERHUBREPO
    - Extension Name: OpticalFlow
    - Docker image: YOURDOCKERHUBUSER/YOURDOCKERHUBREPO
    - Dockertag: latest
    - Settings: add the lines below after replacing the capitalised values with your DockerHub username and repository name

```
{
  "ExposedPorts": {
    "8000/tcp": {}
  },
  "HostConfig": {
    "Binds":[
      "/usr/blueos/extensions/opticalflow/settings:/app/settings",
      "/usr/blueos/extensions/opticalflow/logs:/app/logs"
      ],
    "CpuQuota": 100000,
    "CpuPeriod": 100000,
    "ExtraHosts": [
      "host.docker.internal:host-gateway"
    ],
    "PortBindings": {
      "8000/tcp": [
        {
          "HostPort": ""
        }
      ]
    }
  }
}
```

  - "OpticalFlow" should appear in list of installed extensions and "Status" should appear as "Up xx seconds"

To test on an Ubuntu PC

- Ensure the PC and camera is on the same ethernet subnet
- Open docker desktop (required only on Windows WSL2 machines)
- docker build -t YOURDOCKERHUBUSER/YOURDOCKERHUBREPO:latest .
- docker run -p 8000:8000 YOURDOCKERHUBUSER/YOURDOCKERHUBREPO:latest
- On docker desktop, Containers, a new image should appear with "Port(s)" field, "8000:8000".  Click to open a browser
- Within the web browser the Optical Flow page should appear, set the "IP Address" field to the IP address of the camera
