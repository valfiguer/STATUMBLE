# 📊 STATUMBLE

Real-time Bumble likes viewer with statistics, monitoring, and AutoLike functionality.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ Features

- 🔍 **Real-time Monitoring** - See who liked you on Bumble in real-time
- 📊 **Statistics Dashboard** - Visualize your activity with charts
- 💕 **Match History** - Browse all your matches with search and filters
- 🤖 **AutoLike** - Automatic liking with configurable delay
- 📱 **Multi-page Interface** - Monitor, Matches, History, Statistics
- 💾 **Session Persistence** - Save cookies to avoid repeated logins
- 🔔 **Live Notifications** - Get notified of new likes across all pages

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Google Chrome browser
- ChromeDriver (automatically managed by Selenium)

### Installation

```bash
# Clone the repository
git clone https://github.com/valfiguer/STATUMBLE.git
cd STATUMBLE

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python bumble_web.py
```

### Usage

1. Open your browser at `http://localhost:5555`
2. Click "Iniciar Monitoreo" to start
3. Log in to Bumble in the opened Chrome window
4. Navigate through Bumble to capture likes data
5. View your statistics in the different pages

## 📁 Project Structure

```
STATUMBLE/
├── bumble_web.py      # Main Flask application
├── database.py        # SQLite database operations
├── bumble.py          # Simple launcher
├── requirements.txt   # Python dependencies
├── static/
│   └── css/
│       └── style.css  # Application styles
└── templates/
    ├── index.html     # Main monitor page
    ├── matches.html   # Matches grid view
    ├── historial.html # History table view
    └── stats.html     # Statistics dashboard
```

## 🛠️ Tech Stack

- **Backend**: Flask + Flask-SocketIO
- **Browser Automation**: Selenium WebDriver
- **Database**: SQLite
- **Charts**: Chart.js
- **Real-time**: Socket.IO

## ⚠️ Disclaimer

This tool is for educational purposes only. Use responsibly and in accordance with Bumble's Terms of Service. The developers are not responsible for any misuse or account restrictions.

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

Made with 💛 for data enthusiasts
