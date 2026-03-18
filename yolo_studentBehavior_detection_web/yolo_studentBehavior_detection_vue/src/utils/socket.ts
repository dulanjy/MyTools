import { io } from 'socket.io-client';
 
export class SocketService {
  private socket;
 
  constructor() {
    const socketBase = import.meta.env.VITE_FLASK_SOCKET_URL || import.meta.env.VITE_FLASK_BASE_URL || 'http://localhost:5000';
    this.socket = io(socketBase);
  }
 
  on(event: string, callback: Function) {
    this.socket.on(event, (data) => callback(data.data));
  }
 
  emit(event: string, data: any) {
    this.socket.emit(event, data);
  }
 
  disconnect() {
    this.socket.disconnect();
  }
}
