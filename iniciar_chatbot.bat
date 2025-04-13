@echo off
title Rasa Chatbot - Iniciar

:: Ruta al entorno virtual (ajusta si tienes otro nombre o ubicación)
set VENV=venv_rasa

:: Activar el entorno virtual y correr el action server
start cmd /k "call %VENV%\Scripts\activate && rasa run actions"

:: Pausa para esperar que el servidor de acciones inicie
timeout /t 5 /nobreak > nul

:: Activar el entorno virtual y correr el shell del bot
start cmd /k "call %VENV%\Scripts\activate"
