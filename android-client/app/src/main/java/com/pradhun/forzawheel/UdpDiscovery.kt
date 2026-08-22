package com.pradhun.forzawheel

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException

object UdpDiscovery {
    
    suspend fun discoverServer(port: Int = 12345): String? = withContext(Dispatchers.IO) {
        var udpSocket: DatagramSocket? = null
        try {
            udpSocket = DatagramSocket()
            udpSocket.broadcast = true
            udpSocket.soTimeout = 3000
            
            val msg = "DISCOVER_SERVER".toByteArray()
            val packet = DatagramPacket(
                msg, 
                msg.size, 
                InetAddress.getByName("255.255.255.255"), 
                port
            )
            udpSocket.send(packet)
            
            val recvBuf = ByteArray(1024)
            val recvPacket = DatagramPacket(recvBuf, recvBuf.size)
            
            udpSocket.receive(recvPacket)
            
            val response = String(recvPacket.data, 0, recvPacket.length).trim()
            Log.i("UdpDiscovery", "Received discovery response: $response")
            
            // Expected format: IP:PORT
            return@withContext response.split(":")[0]
            
        } catch (e: SocketTimeoutException) {
            Log.w("UdpDiscovery", "Discovery timeout")
            return@withContext null
        } catch (e: Exception) {
            Log.e("UdpDiscovery", "Discovery failed", e)
            return@withContext null
        } finally {
            udpSocket?.close()
        }
    }
}
