import { io } from 'socket.io-client';
import { ensureAccessToken } from './api';

let socket = null;

export async function connectSocket() {
  if (socket?.connected) return socket;

  const token = await ensureAccessToken();
  if (!token) throw new Error('not authenticated');

  if (socket) {
    socket.auth = { token };
    socket.connect();
    return socket;
  }

  socket = io({
    autoConnect: true,
    auth: { token },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 500,
    reconnectionDelayMax: 5000,
  });

  // Socket.IO reconnects the transport on its own, but the server authenticates on
  // every connect and has no memory of the previous session. A 15-minute access token
  // can easily expire during a duel, so refresh it before each reconnect attempt or
  // the reconnect is refused and the player silently forfeits.
  socket.io.on('reconnect_attempt', async () => {
    try {
      const fresh = await ensureAccessToken();
      socket.auth = { token: fresh };
    } catch {
      /* the session is gone; the connect will be refused and the UI will show it */
    }
  });

  return socket;
}

export function getSocket() {
  return socket;
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}
