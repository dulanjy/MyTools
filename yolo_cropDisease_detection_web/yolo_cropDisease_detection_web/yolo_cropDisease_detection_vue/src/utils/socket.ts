import { io } from 'socket.io-client';
 
export class SocketService {
  private socket;
 
  constructor() {
    const socketBaseUrl = import.meta.env.VITE_FLASK_SOCKET_URL || 'http://localhost:5000';
    this.socket = io(socketBaseUrl);
  }
 
  on(event: string, callback: Function) {
    this.socket.on(event, (data) => {
      const normalized = data && typeof data === 'object' && 'data' in data ? (data as any).data : data;
      callback(normalized);
    });
  }
 
  emit(event: string, data: any) {
    this.socket.emit(event, data);
  }
 
  disconnect() {
    this.socket.disconnect();
  }
}
