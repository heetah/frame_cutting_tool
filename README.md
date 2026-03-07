# CV Project: Timeline Frame Extractor ?

A high-speed, GUI-based video frame extraction tool built with Python and FFmpeg. This tool is designed for Computer Vision data preprocessing, specifically for extracting fine-grained action frames (e.g., littering behavior) from surveillance videos.

## Features
- **Dual-Handle Timeline:** Intuitive UI for precise Start/End point selection.
- **Instant Preview:** Real-time frame rendering using OpenCV.
- **High-Speed Extraction:** Leverages FFmpeg for rapid, hardware-accelerated frame decoding.
- **Auto-Naming:** Prevents overwriting old datasets by using timestamped prefixes.

## Prerequisites
**Important:** This tool requires `FFmpeg` to be installed on your system.

**For Windows Users:**
Open PowerShell and run:
`winget install Gyan.FFmpeg`
*(Restart your terminal after installation)*

## Installation
1. Clone the repository:
   ```bash
    git clone https://github.com/heetah/frame_cutting_tool.git
    cd your-repo-name
3. Create a Conda environment (Recommended):
   ```bash
    conda create -n cv_env python=3.10
    conda activate cv_env
5. Install Python dependencies:
    ```python
    pip install -r requirements.txt
6. Run the application
   ```python
    python main.py
