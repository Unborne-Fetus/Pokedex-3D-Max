package com.unbornefetus.pokedex3dmax

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import java.io.ByteArrayInputStream
import java.io.FileNotFoundException

/**
 * The Android version uses the same index.html as the desktop/web editions.
 * All packaged assets use a local HTTPS origin, so JS fetch and SubtleCrypto
 * also work offline. No retired SceneView/Compose implementation is loaded.
 */
class MainActivity : Activity() {
    private companion object {
        const val APP_HOST = "pokedex3d.local"
        const val APP_URL = "https://pokedex3d.local/index.html"
        const val PICK_FILE = 4201
    }

    private lateinit var webView: WebView
    private var pendingFileSelection: ValueCallback<Array<Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this).apply {
            setBackgroundColor(Color.rgb(11, 18, 32))
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                allowFileAccess = false
                allowContentAccess = true
                mediaPlaybackRequiresUserGesture = false
                loadsImagesAutomatically = true
                useWideViewPort = true
                loadWithOverviewMode = false
                setSupportZoom(false)
            }
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(
                    view: WebView, request: WebResourceRequest
                ): Boolean {
                    val uri = request.url
                    if (uri.scheme == "https" && uri.host == APP_HOST) return false
                    if (request.isForMainFrame && (uri.scheme == "http" || uri.scheme == "https")) {
                        startActivity(Intent(Intent.ACTION_VIEW, uri))
                        return true
                    }
                    return false
                }

                override fun shouldInterceptRequest(
                    view: WebView, request: WebResourceRequest
                ): WebResourceResponse? {
                    val uri = request.url
                    if (uri.scheme != "https" || uri.host != APP_HOST) return null
                    val path = uri.path?.removePrefix("/") ?: ""
                    if (path.isBlank() || path.split('/').any { it == ".." || it.isBlank() }) {
                        return response("text/plain", "Invalid bundled asset", 404)
                    }
                    return try {
                        val stream = assets.open(path)
                        WebResourceResponse(mime(path), "UTF-8", 200, "OK",
                            mapOf("Access-Control-Allow-Origin" to "*"), stream)
                    } catch (_: FileNotFoundException) {
                        response("text/plain", "Asset not installed", 404)
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    view: WebView,
                    callback: ValueCallback<Array<Uri>>,
                    params: WebChromeClient.FileChooserParams
                ): Boolean {
                    pendingFileSelection?.onReceiveValue(null)
                    pendingFileSelection = callback
                    return try {
                        startActivityForResult(params.createIntent(), PICK_FILE)
                        true
                    } catch (_: Exception) {
                        pendingFileSelection = null
                        callback.onReceiveValue(null)
                        false
                    }
                }
            }
        }
        setContentView(webView)
        if (savedInstanceState == null) webView.loadUrl(APP_URL)
        else webView.restoreState(savedInstanceState)
    }

    private fun mime(path: String): String = when {
        path.endsWith(".html", true) -> "text/html"
        path.endsWith(".js", true) -> "text/javascript"
        path.endsWith(".css", true) -> "text/css"
        path.endsWith(".json", true) -> "application/json"
        path.endsWith(".wasm", true) -> "application/wasm"
        path.endsWith(".glb", true) -> "model/gltf-binary"
        path.endsWith(".png", true) -> "image/png"
        path.endsWith(".jpg", true) || path.endsWith(".jpeg", true) -> "image/jpeg"
        path.endsWith(".svg", true) -> "image/svg+xml"
        path.endsWith(".woff2", true) -> "font/woff2"
        else -> "application/octet-stream"
    }

    private fun response(type: String, message: String, code: Int): WebResourceResponse =
        WebResourceResponse(type, "UTF-8", code, "Not Found",
            emptyMap(), ByteArrayInputStream(message.toByteArray()))

    @Deprecated("Used for the native Android file picker.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == PICK_FILE) {
            pendingFileSelection?.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            pendingFileSelection = null
        }
    }

    @Deprecated("Android back navigation is delegated to the WebView.")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        pendingFileSelection?.onReceiveValue(null)
        pendingFileSelection = null
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
