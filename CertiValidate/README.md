# CertiValidate - Final Year Project

A comprehensive AI & Blockchain Based Certificate Validation System built with Python, Flask, ML, and a custom implementation of SHA-256 Blockchain.


Live Proj : https://certivalidate.vercel.app/

## Features
- **Custom Blockchain:** SHA-256 encrypted block generation for each certificate.
- **AI Authenticity Analysis:** Utilizes Pytesseract (OCR) and TF-IDF Cosine Similarity to detect fake certificates based on textual similarities and patterns.
- **Role-based Authentication:** Verifiers and Admins.
- **PDF Reports:** Downloadable QR-code attached Verification Reports.
- **Stunning UI:** Glassmorphism, AOS animations, Lottie JS files, Bootstrap 5.

## Requirements
**NOTE:** You must have Tesseract-OCR installed on your machine for the AI image text extraction to function correctly. 
Download it from: https://github.com/UB-Mannheim/tesseract/wiki
Add the installation path to your system's Environment Variables (PATH) or configure it directly in `ai_module.py`.

## Quick Start (Run locally)
1. **Navigate to project directory.**
2. **Install Python dependencies:**
   `pip install -r requirements.txt`
3. **Initialize Database** (already initialized in deployment, but good for reset):
   `python database.py`
4. **Run Application:**
   `python app.py`
5. **Open Browser:**
   `http://127.0.0.1:5000`

## Author
Professionally built Full Stack Web Application.
