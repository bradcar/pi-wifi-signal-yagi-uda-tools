
# PyCharm Remote Deployment Reset Guide

On renaming my project and pushing to GitHub, PyCharm's internal tracking broke, making remote development on the Raspberry Pi incredibly difficult.
The PyCharm SSH remote interpreter insisted on running code out of a randomized path like `/tmp/<randomstring>/` instead of the project's actual remote directory.
It also occasionally threw ghost credential errors.

To completely reset PyCharm's global and project-level memory, follow these steps:


## Step 1: Remove Old Remote Configurations:
Before wiping the caches, strip out all active links to the remote target within the PyCharm UI:

* **Python Interpreters:** Go to `Settings/Preferences` ➔ `Project` ➔ `Python Interpreter`. Click **Show All...**, highlight any remote interpreters, and click the **- (Minus icon)** until the list is blank. Click **Apply**.
* **Deployment Servers:** Go to `Tools` ➔ `Deployment` ➔ `Configuration`. Highlight any server profiles in the left column and click the **- (Minus icon)** until it's completely empty. Click **Apply**.
* **SSH Configurations:** Go to `Tools` ➔ `SSH Configurations`. Delete every single entry here using the **- (Minus icon)**. Click **Apply** and **OK**.

## Step 2: Purge Cache & Configuration Files:
Quit PyCharm completely. Open the laptop Terminal, navigate to local project directory, and run the following to destroy the local project database and global JetBrains application caches:

```bash
rm -rf .idea

rm -rf ~/Library/Caches/JetBrains/PyCharm*/remote_sources/
rm -rf ~/Library/Caches/JetBrains/PyCharm*/project_caches/
```
## Step 3: Pristine Re-Configuration (After Restarting navigate to your project):
1. Go to Tools ➔ Deployment ➔ Configuration.
   1. Click the + icon, select SFTP, and authenticate your SSH connection to the Pi.
   2. Switch to the Mappings tab. Set the Local path to your Mac project folder, and explicitly hardcode the Deployment path on your Pi (/home/pi-admin/pi-wifi-signal-yagi-uda-tools).
   3. Click the Checkmark icon (Set as Default) above the server list, then click Apply.
2. Add the Remote Interpreter:
   1. Go to Project ➔ Python Interpreter ➔ Add Interpreter ➔ On SSH...
   2. Select Existing configuration and choose the SFTP deployment server you just created.
   3. On the final configuration screen, ensure the Python interpreter path is correct (/usr/bin/python3) and double-check that the folder synchronization path matches your permanent home directory on the Pi, rather than a /tmp/ directory. Click Finish.
3. Trigger Initial Manual Sync:
   1. Right-click your top-level project folder in the PyCharm project sidebar.
   2. Select Deployment ➔ Upload to... and choose your Pi. Wait for the file transfer to complete.
4. Create a Dedicated Run Configuration:
   1. Click the run dropdown in the top-right corner of PyCharm and select Edit Configurations...
   2. Click + ➔ Python.
   3. Set the Script path to your primary local execution script.
   4. Ensure the Python interpreter is set to your newly created Remote SSH instance.
   5. Set the Working directory explicitly to your permanent project folder on the Pi.
   6. Click Apply and OK.

Click the green Play arrow. The execution pipeline will now bypass the broken automated tracking layer, running your code natively out of its true remote directory.