@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Comfy-Luna-Core: Claude Code CLI Installer
echo ============================================
echo.

:: Detect ComfyUI root (bat file is in custom_nodes/comfy-luna-core/)
set "LUNA_DIR=%~dp0"
set "COMFYUI_ROOT=%LUNA_DIR%..\.."

:: Resolve to absolute path
pushd "%COMFYUI_ROOT%" 2>nul
if errorlevel 1 (
    echo [ERROR] Could not find ComfyUI root at: %COMFYUI_ROOT%
    echo         Make sure this extension is installed in ComfyUI/custom_nodes/comfy-luna-core/
    goto :fail
)
set "COMFYUI_ROOT=%CD%"
popd

echo [INFO] ComfyUI root: %COMFYUI_ROOT%
echo [INFO] Luna Core:    %LUNA_DIR%
echo.

:: Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo         Download from: https://nodejs.org/
    goto :fail
)

for /f "tokens=*" %%v in ('node --version') do set "NODE_VER=%%v"
echo [OK] Node.js found: %NODE_VER%

:: Check npm
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm is not installed or not in PATH.
    goto :fail
)

:: Check if Claude Code is already installed
where claude >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('claude --version 2^>nul') do set "CLAUDE_VER=%%v"
    echo [OK] Claude Code already installed: !CLAUDE_VER!
    echo      Skipping npm install, proceeding to CLAUDE.md setup...
    goto :setup_claude_md
)

:: Install Claude Code CLI
echo.
echo [INSTALL] Installing Claude Code CLI globally...
echo.
call npm install -g @anthropic-ai/claude-code
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install Claude Code CLI.
    echo         Try running this script as Administrator.
    goto :fail
)

echo.
echo [OK] Claude Code CLI installed successfully.

:: Verify installation
where claude >nul 2>&1
if errorlevel 1 (
    echo [WARN] 'claude' command not found in PATH after install.
    echo        You may need to restart your terminal.
)

:setup_claude_md
echo.
echo [SETUP] Creating CLAUDE.md in ComfyUI root...

:: Write CLAUDE.md
(
echo # ComfyUI Project Context
echo.
echo This is a ComfyUI installation with the Comfy-Luna-Core AI assistant extension.
echo.
echo ## Project Structure
echo.
echo - `ComfyUI/` — Main ComfyUI application
echo - `custom_nodes/` — Installed custom node packs
echo - `custom_nodes/comfy-luna-core/` — Luna Core AI assistant extension
echo - `models/` — Model files ^(checkpoints, LoRAs, VAEs, etc.^)
echo - `output/` — Generated images and videos
echo - `input/` — Input images for workflows
echo - `user/default/workflows/` — Saved user workflows
echo.
echo ## Luna Core Extension
echo.
echo Luna Core is an AI agent framework that provides:
echo - 16 real-time tools for node discovery, model inspection, workflow manipulation, and execution
echo - 31 official Comfy-Org workflow templates
echo - Auto-generated knowledge from the installation ^(nodes, models, metadata^)
echo - 7 interchangeable AI backends ^(Gemini, OpenAI, Ollama, Claude Code, etc.^)
echo - Model metadata intelligence ^(trigger words, base model, recommended settings^)
echo - Direct canvas modification and auto-arrange
echo - Execution feedback loop ^(queue, test, diagnose, fix^)
echo.
echo Key files:
echo - `custom_nodes/comfy-luna-core/controller.py` — HTTP API, agent coordination, tool loop
echo - `custom_nodes/comfy-luna-core/agents/` — AI backend implementations
echo - `custom_nodes/comfy-luna-core/agents/comfyui_tools.py` — 14 ComfyUI tools
echo - `custom_nodes/comfy-luna-core/knowledge/` — Context-aware knowledge system
echo - `custom_nodes/comfy-luna-core/templates/` — Workflow registry and official templates
echo - `custom_nodes/comfy-luna-core/validation/` — 7-check workflow validator
echo - `custom_nodes/comfy-luna-core/web/panel.js` — Chat UI frontend
echo.
echo ## ComfyUI Concepts
echo.
echo - **Nodes**: Processing units with typed inputs/outputs ^(MODEL, CLIP, LATENT, IMAGE, etc.^)
echo - **Workflows**: Node graphs saved as JSON ^(UI format with LiteGraph or API format^)
echo - **Widgets**: Node parameters ^(INT, FLOAT, STRING, COMBO dropdowns^)
echo - **Models**: Checkpoints, LoRAs, VAEs, ControlNets, upscalers, embeddings
echo - **extra_model_paths.yaml**: Additional model directories outside default paths
echo.
echo ## When Working on This Project
echo.
echo - The Python environment is the ComfyUI embedded Python, not system Python
echo - Custom nodes register via `NODE_CLASS_MAPPINGS` in `__init__.py`
echo - Frontend extensions use `WEB_DIRECTORY` to serve JS files
echo - Routes register on `PromptServer.instance.routes`
echo - ComfyUI API is at `http://127.0.0.1:8188`
echo - Node definitions available at `/object_info`
) > "%COMFYUI_ROOT%\CLAUDE.md"

echo [OK] CLAUDE.md created at: %COMFYUI_ROOT%\CLAUDE.md
echo.

:: Final instructions
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo Next steps:
echo   1. Open a terminal in your ComfyUI directory:
echo      cd %COMFYUI_ROOT%
echo.
echo   2. Run Claude Code:
echo      claude
echo.
echo   3. Login with your Claude Max or Pro account
echo.
echo   4. Start asking questions about your ComfyUI setup!
echo.
echo CLAUDE.md provides project context so Claude understands
echo your ComfyUI installation structure automatically.
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed. See errors above.
echo.
pause
exit /b 1
