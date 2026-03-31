# Video AI Anomaly Detection System

A comprehensive Flask-based web application for video surveillance and anomaly detection using AI. This system allows users to upload videos, detect anomalies in real-time, manage cameras, and monitor live streams with advanced AI-powered analysis.

## Features

- **User Authentication & Authorization**: Secure login/signup with role-based access (Admin/Client)
- **Video Upload & Management**: Upload and organize video files for analysis
- **Real-time Anomaly Detection**: AI-powered detection using YOLOv8 for identifying unusual activities
- **Live Camera Streaming**: Support for live camera feeds with anomaly monitoring
- **Dashboard Analytics**: Comprehensive dashboard with anomaly statistics and charts
- **Camera Management**: Add and manage multiple cameras for surveillance
- **Subscription System**: Tiered subscription plans for different user levels
- **Admin Panel**: Full administrative controls for user and system management
- **Notification System**: Alerts for detected anomalies
- **Export Functionality**: Export reports and data
- **Support System**: Integrated ticketing system for user support

## Technology Stack

- **Backend**: Flask (Python web framework)
- **Database**: MongoDB (NoSQL database)
- **AI/ML**: YOLOv8 (Ultralytics), OpenCV, NumPy, SciPy
- **Frontend**: HTML, CSS, JavaScript
- **Authentication**: bcrypt for password hashing
- **Deployment**: Ready for deployment on cloud platforms

## Installation

### Prerequisites

- Python 3.8+
- MongoDB
- Git

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/video-ai-anomaly-detection.git
   cd video-ai-anomaly-detection
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   # On Windows
   .venv\Scripts\activate
   # On macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```
   MONGO_URI=mongodb://localhost:27017/video_ai
   SECRET_KEY=your_secret_key_here
   FLASK_ENV=development
   ```

5. **Set up MongoDB**
   - Install and start MongoDB
   - Create database: `video_ai`

6. **Run the application**
   ```bash
   python run.py
   ```

7. **Access the application**
   Open your browser and go to `http://localhost:5000`

## Usage

### For Users
1. Register/Login to access the dashboard
2. Upload videos for anomaly detection
3. View detected anomalies and analytics
4. Manage camera feeds and live streams

### For Admins
1. Access admin panel for system management
2. Manage users, cameras, and subscriptions
3. View system-wide analytics and reports

## Project Structure

```
video-ai-anomaly-detection/
├── app.py                 # Main Flask application
├── run.py                 # Application runner
├── config.py             # Configuration settings
├── requirements.txt      # Python dependencies
├── yolov8n.pt           # YOLOv8 model weights
├── anomaly_engine/       # AI anomaly detection engine
│   ├── detector.py
│   ├── yolo_model.py
│   └── anomaly_classifier.py
├── database/             # Database setup and connections
├── models/               # Data models
├── routes/               # Flask blueprints/routes
├── services/             # Business logic services
├── static/               # Static files (CSS, JS, images)
├── templates/            # HTML templates
├── uploads/              # Uploaded files
├── utils/                # Utility functions
└── recordings/           # Video recordings
```

## API Endpoints

- `GET /` - Home page (redirects to dashboard/login)
- `GET /dashboard` - Main dashboard
- `POST /auth/login` - User login
- `POST /auth/signup` - User registration
- `GET /video/upload` - Video upload page
- `POST /video/upload` - Upload video file
- `GET /live` - Live camera streams
- `GET /anomaly` - Anomaly detection results
- `GET /admin` - Admin panel

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please create a ticket through the application's support system or contact the development team.

## Acknowledgments

- YOLOv8 by Ultralytics for object detection
- Flask framework for web development
- OpenCV for computer vision tasks
- MongoDB for database management