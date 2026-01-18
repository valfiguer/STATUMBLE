#!/usr/bin/env python3
"""
🐝 Bumble Likes Viewer - Launcher
=================================

Este script inicia la interfaz web moderna.
"""

import os
import sys
import webbrowser
from time import sleep

def main():
    print("\n" + "="*60)
    print("🐝 BUMBLE LIKES VIEWER")
    print("="*60)
    print("\n📝 Iniciando servidor web...")
    print("🌐 Se abrirá http://localhost:5555 en tu navegador")
    print("="*60 + "\n")
    
    # Abrir navegador después de un segundo
    def open_browser():
        sleep(2)
        webbrowser.open('http://localhost:5555')
    
    import threading
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Ejecutar bumble_web.py
    os.system(f'{sys.executable} bumble_web.py')


if __name__ == "__main__":
    main()
