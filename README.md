# BlueOS Extension Template

This template provides you a foundation to kickstart your journey as a BlueOS extensions developer!
Please follow the instructions to launch your first BlueOS application.


## Instructions

### Creating Your Extension
Start by creating your extension using this template as a base. Simply navigate to the upper menu and select "Use this template."

### Building the Extension

To build your BlueOS extension, follow the steps below:

#### For Direct Raspberry Use

1. Navigate to your extension's source code.

2. Execute the following command to build your extension:

   ```shell
   docker build .
    ```

#### For build it from your computer or CI, use docker buildx:
1. Execute the following command to build your extension:

   ```shell
   docker buildx build --platform linux/arm/v7 . -t my_docker_user/my_blueos_extension:latest --output type=registry
    ```


### Running your extension:

To run your BlueOS extension, follow these steps:

#### Within BlueOS
1. Navigate to Extensions > Installed and click the Add button to create and launch your extension from BlueOS.

#### Manual use

2. For Raspberry Pi users, you can also manually run your extension by executing the following command:
   ```shell
   docker run --detach --publish 9999:80 my_docker_user/my_blueos_extension:latest
    ```