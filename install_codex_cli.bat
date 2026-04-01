@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Comfy-Luna-Core: OpenAI Codex CLI Installer
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

:: Check if Codex is already installed
where codex >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('codex --version 2^>nul') do set "CODEX_VER=%%v"
    echo [OK] Codex CLI already installed: !CODEX_VER!
    echo      Skipping npm install, proceeding to setup...
    goto :setup_instructions
)

:: Install Codex CLI
echo.
echo [INSTALL] Installing OpenAI Codex CLI globally...
echo.
call npm install -g @openai/codex
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install Codex CLI.
    echo         Try running this script as Administrator.
    goto :fail
)

echo.
echo [OK] Codex CLI installed successfully.

:: Verify installation
where codex >nul 2>&1
if errorlevel 1 (
    echo [WARN] 'codex' command not found in PATH after install.
    echo        You may need to restart your terminal.
)

:setup_instructions
echo.

:: Check for OPENAI_API_KEY
if defined OPENAI_API_KEY (
    echo [OK] OPENAI_API_KEY is set.
) else (
    echo [INFO] OPENAI_API_KEY is not set — that's fine.
    echo        Codex works with ChatGPT Plus/Pro login (no API key needed^).
    echo        Just run 'codex' and it will prompt you to sign in.
    echo        Alternatively, set an API key: set OPENAI_API_KEY=sk-xxxxx
    echo.
)

:: Write CODEX.md (Codex uses AGENTS.md or project docs for context)
echo [SETUP] Creating codex_instructions.md in ComfyUI root...

(
echo # ComfyUI Project Context for Codex
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
) > "%COMFYUI_ROOT%\codex_instructions.md"

echo [OK] codex_instructions.md created at: %COMFYUI_ROOT%\codex_instructions.md
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
echo   2. Run Codex:
echo      codex
echo.
echo   3. Sign in with your ChatGPT Plus/Pro account (or use an API key)
echo.
echo   4. Start asking questions about your ComfyUI setup!
echo.
echo codex_instructions.md provides project context so Codex
echo understands your ComfyUI installation structure.
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed. See errors above.
echo.
pause
exit /b 1
