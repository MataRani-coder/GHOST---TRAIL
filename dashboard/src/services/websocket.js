import soundManager from './audioAlert';

// Use current page host for WebSocket (Vite proxies /api/ws → port 8765)
const getWsUrl = () => {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ws`;
};

class WebSocketManager {
  constructor() {
    this.socket = null;
    this.listeners = {};
    this.reconnectTimeout = null;
    this.reconnectDelay = 2000;
    this.maxReconnectDelay = 20000;
    this.isConnected = false;
    this.isConnecting = false;
    this.mockInterval = null;
    this.seenAlerts = new Set();
    this._pingInterval = null;
  }

  connect() {
    if (this.isConnected || this.isConnecting) return;

    this.isConnecting = true;
    const wsUrl = getWsUrl();
    console.log(`[Sentinel WS] Connecting to ${wsUrl}...`);

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.isConnected = true;
        this.isConnecting = false;
        this.reconnectDelay = 2000;
        console.log('[Sentinel WS] Connection established with AI core.');
        this.stopMockDataGenerator();
        this.emit('connection_change', { status: 'connected' });

        // Keep-alive heartbeat every 10s
        if (this._pingInterval) clearInterval(this._pingInterval);
        this._pingInterval = setInterval(() => {
          if (this.isConnected && this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send('ping');
          }
        }, 10000);
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data && data.type === 'telemetry') {
            this.emit('telemetry', {
              timestamp: new Date().toISOString(),
              fps: data.fps,
              active_cameras: (data.cameras || []).length,
              detections: data.active_alerts || 0,
              status: data.status,
              alerts: data.alerts || [],
            });

            // Trigger alerts from telemetry
            if (data.alerts && Array.isArray(data.alerts)) {
              data.alerts.forEach(alert => {
                const id = alert.id || `${alert.timestamp}-${alert.camera_id}`;
                if (!this.seenAlerts.has(id)) {
                  this.seenAlerts.add(id);
                  this.emit('alert', alert);
                  soundManager.playWarning();
                }
              });
            }
          } else if (data && data.type === 'alert') {
            const id = data.id || `${data.timestamp}-${data.camera_id}`;
            if (!this.seenAlerts.has(id)) {
              this.seenAlerts.add(id);
              this.emit('alert', data);
              soundManager.playCriticalAlert();
            }
          } else if (data && data.type === 'init') {
            this.emit('init', data);
          } else if (data && data.type === 'shutdown') {
            this.emit('shutdown', data);
          } else if (data && data.event) {
            this.emit(data.event, data.data);
          }
        } catch (err) {
          console.warn('[Sentinel WS] Error parsing incoming frame:', err);
        }
      };

      this.socket.onclose = () => {
        this.isConnected = false;
        this.isConnecting = false;
        if (this._pingInterval) clearInterval(this._pingInterval);
        this.emit('connection_change', { status: 'disconnected' });
        this.scheduleReconnect();
      };

      this.socket.onerror = () => {
        if (this.socket) this.socket.close();
      };
    } catch (error) {
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);

    // Fall back to simulator if server is offline
    this.startMockDataGenerator();

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    if (this._pingInterval) clearInterval(this._pingInterval);
    if (this.socket) {
      this.socket.close();
    }
    this.stopMockDataGenerator();
  }

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
  }

  off(event, callback) {
    if (!this.listeners[event]) return;
    this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          console.error(`Error in event listener for ${event}:`, e);
        }
      });
    }
  }

  send(event, data) {
    if (this.isConnected && this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ event, data }));
    }
  }

  // Realistic mock simulator for offline / presentation mode
  startMockDataGenerator() {
    if (this.mockInterval) return;

    this.emit('connection_change', { status: 'simulated' });
    let guestCounter = 940;

    this.mockInterval = setInterval(() => {
      // 1. Telemetry heartbeat
      const tickFps = (28.0 + (Math.sin(Date.now() / 2000) * 1.5) + (Math.random() * 0.4)).toFixed(1);
      this.emit('telemetry', {
        timestamp: new Date().toISOString(),
        fps: parseFloat(tickFps),
        active_cameras: 3,
        status: 'running',
        active_alerts: 1,
      });

      // 2. Periodic dynamic detection event (every ~6-10s)
      if (Math.random() > 0.4) {
        const cameras = ['cam_1', 'cam_2', 'cam_3'];
        const targetCam = cameras[Math.floor(Math.random() * cameras.length)];
        const isKnown = Math.random() > 0.35;
        let detectedName = '';
        
        if (isKnown) {
          const knownList = ['Ganesh', 'Lakshya', 'Ansh', 'Ashwini'];
          detectedName = knownList[Math.floor(Math.random() * knownList.length)];
        } else {
          detectedName = `Guest_${guestCounter++}`;
        }

        const detectionEvent = {
          camera_id: targetCam,
          name: detectedName,
          confidence: parseFloat((0.82 + Math.random() * 0.16).toFixed(2)),
          timestamp: Date.now(),
          is_known: isKnown,
          track_id: Math.floor(Math.random() * 80) + 1,
          bbox: [
            Math.floor(60 + Math.random() * 120),
            Math.floor(40 + Math.random() * 100),
            Math.floor(220 + Math.random() * 100),
            Math.floor(300 + Math.random() * 80),
          ]
        };

        this.emit('detection', detectionEvent);

        // Rare simulated alert
        if (!isKnown && Math.random() > 0.75) {
          const simAlert = {
            id: `sim-${Date.now()}`,
            alert_type: 'unknown_person',
            type: 'unknown_person',
            camera_id: targetCam,
            message: `Unidentified Individual Detected in ${targetCam.toUpperCase()}`,
            detail: `Target matched unassigned track ID #${detectionEvent.track_id} (${detectedName}).`,
            timestamp: Date.now() / 1000,
            status: 'active',
            severity: 'warning'
          };
          this.emit('alert', simAlert);
          soundManager.playWarning();
        }
      }
    }, 3500);
  }

  stopMockDataGenerator() {
    if (this.mockInterval) {
      clearInterval(this.mockInterval);
      this.mockInterval = null;
    }
  }
}

export const wsService = new WebSocketManager();
export default wsService;
