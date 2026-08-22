package com.pradhun.forzawheel

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.DataOutputStream
import java.io.IOException
import java.net.Socket
import java.net.SocketTimeoutException

class TcpClient(private val scope: CoroutineScope) {

    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private var socket: Socket? = null
    private var outStream: DataOutputStream? = null

    // Channel for buffering commands
    private val commandChannel = Channel<String>(capacity = 100)
    private var senderJob: Job? = null

    sealed class ConnectionState {
        object Disconnected : ConnectionState()
        object Connecting : ConnectionState()
        data class Connected(val ip: String) : ConnectionState()
        data class Error(val message: String) : ConnectionState()
    }

    fun connect(ip: String, port: Int = 12345) {
        if (_connectionState.value is ConnectionState.Connected) return
        _connectionState.value = ConnectionState.Connecting
        
        scope.launch(Dispatchers.IO) {
            try {
                disconnectInternal()
                
                val s = Socket()
                s.tcpNoDelay = true
                s.keepAlive = true
                s.sendBufferSize = 65536
                
                s.connect(java.net.InetSocketAddress(ip, port), 5000)
                socket = s
                outStream = DataOutputStream(s.getOutputStream())
                
                _connectionState.value = ConnectionState.Connected(ip)
                startSenderLoop()
                
            } catch (e: Exception) {
                Log.e("TcpClient", "Connection failed", e)
                _connectionState.value = ConnectionState.Error(e.message ?: "Connection failed")
                disconnectInternal()
            }
        }
    }

    private fun startSenderLoop() {
        senderJob?.cancel()
        senderJob = scope.launch(Dispatchers.IO) {
            try {
                for (cmd in commandChannel) {
                    if (!isActive || outStream == null) break
                    outStream?.writeBytes("$cmd\n")
                    // Removed flush for analog commands to allow Nagle to batch if tcpNoDelay is off,
                    // but we have tcpNoDelay = true, so we flush manually for immediate delivery.
                    outStream?.flush() 
                }
            } catch (e: IOException) {
                Log.e("TcpClient", "Send failed", e)
                _connectionState.value = ConnectionState.Error("Connection lost")
                disconnectInternal()
            }
        }
    }

    fun sendCommand(command: String) {
        if (_connectionState.value is ConnectionState.Connected) {
            val result = commandChannel.trySend(command)
            if (result.isFailure) {
                Log.w("TcpClient", "Command channel full, dropped: $command")
            }
        }
    }

    fun disconnect() {
        scope.launch(Dispatchers.IO) {
            disconnectInternal()
            _connectionState.value = ConnectionState.Disconnected
        }
    }

    private suspend fun disconnectInternal() = withContext(Dispatchers.IO) {
        senderJob?.cancel()
        senderJob = null
        try {
            outStream?.flush()
            socket?.shutdownOutput()
            outStream?.close()
        } catch (_: Exception) {}
        try {
            socket?.close()
        } catch (_: Exception) {}
        socket = null
        outStream = null
    }
}
