# CPIO Library for Houdini Shelf Tools

<img width="1632" height="627" alt="image" src="https://github.com/user-attachments/assets/20d7f582-3586-4386-93c9-3f556a85dd3d" />

## Installation

1. **Clone this repository** into your ComfyUI custom_nodes directory:
   ```bash
   cd "your path"/Documents/
   git clone https://github.com/34drk21/ELDLibrary.git
   ```
   
2. **Install dependencies**:
   ```bash
   cd ELDLibrary
   pip install -r requirements.txt
   ```
   
## Activate the server
to activate the server, you have to run uvicorn and the script runs server.py in scripts folder

```bash
cd scripts
uvicorn server:app --reload --host 0.0.0.0 --port 8080

```
## Shelf in Houdini
1. Create your own custom tools in your shelf and copy `/ELDLibrary
/Houdini_shelf_tools/ELD_Library_UI.py` to script
2. check ipconfig in console and you have to set proper ip address to `API_BASE` in ELD_Library_UI.py
<img width="768" height="689" alt="ELDLib_05" src="https://github.com/user-attachments/assets/c4a3038d-589d-4a90-b5a4-024563e681a4" />
