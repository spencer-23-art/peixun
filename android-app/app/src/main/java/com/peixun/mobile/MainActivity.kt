package com.peixun.mobile

import android.Manifest
import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.io.FileOutputStream
import java.net.URL
import java.util.concurrent.Executors
import javax.net.ssl.HttpsURLConnection

class MainActivity : Activity() {
    companion object {
        private const val TAG = "PeixunDisplay"
        private const val APP_URL = "https://8.148.25.74/"
        private const val APP_HOST = "8.148.25.74"
        private const val FILE_CHOOSER_REQUEST = 1001
        private const val STORAGE_PERMISSION_REQUEST = 1002
    }

    private lateinit var webView: WebView
    private lateinit var errorPanel: View
    private lateinit var errorDetail: TextView
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var pendingDownload: DownloadRequest? = null
    private val downloadExecutor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            configureFullscreenWindow()
            enableImmersiveMode()
            requestPreferredRefreshRate()
            setContentView(createContentView())
            configureWebView()
            webView.loadUrl(APP_URL)
        } catch (_: Exception) {
            // An unavailable WebView provider or an OEM-specific window setting must not
            // terminate the app before the user can see what needs attention.
            showStartupFallback()
        }
    }

    override fun onResume() {
        super.onResume()
        configureFullscreenWindow()
        enableImmersiveMode()
        requestPreferredRefreshRate()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) enableImmersiveMode()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            moveTaskToBack(true)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != FILE_CHOOSER_REQUEST) return
        val callback = fileChooserCallback ?: return
        fileChooserCallback = null
        callback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != STORAGE_PERMISSION_REQUEST) return
        val request = pendingDownload
        pendingDownload = null
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED && request != null) {
            downloadFile(request)
        } else {
            Toast.makeText(this, "未取得存储权限，无法保存下载文件", Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        if (::webView.isInitialized) {
            webView.destroy()
        }
        downloadExecutor.shutdownNow()
        super.onDestroy()
    }

    private fun createContentView(): View {
        val root = FrameLayout(this).apply { setBackgroundColor(Color.rgb(15, 23, 42)) }
        webView = WebView(this)
        root.addView(webView, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))
        // Keep scrolling and CSS compositing on the GPU.  This is the normal
        // WebView default, but stating it explicitly avoids OEM fallbacks.
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.overScrollMode = View.OVER_SCROLL_NEVER

        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
            setBackgroundColor(Color.rgb(15, 23, 42))
            visibility = View.GONE
        }
        val title = TextView(this).apply {
            text = "暂时无法连接服务器"
            setTextColor(Color.WHITE)
            textSize = 20f
            gravity = Gravity.CENTER
        }
        errorDetail = TextView(this).apply {
            text = "请检查网络后重试"
            setTextColor(Color.rgb(203, 213, 225))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, dp(22))
        }
        val retry = Button(this).apply {
            text = "重新连接"
            setOnClickListener {
                hideConnectionError()
                webView.loadUrl(APP_URL)
            }
        }
        panel.addView(title)
        panel.addView(errorDetail)
        panel.addView(retry, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.CENTER })
        root.addView(panel, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))
        errorPanel = panel
        return root
    }

    @Suppress("SetJavaScriptEnabled")
    private fun configureWebView() {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = true
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = "$userAgentString PeixunMobile/1.0"
        }
        CookieManager.getInstance().setAcceptCookie(true)

        // Some Android 9/10 builds reveal the status bar again after a WebView
        // navigation or a file picker returns. Re-apply immersive mode once the
        // system has finished its own visibility update.
        webView.setOnSystemUiVisibilityChangeListener {
            webView.postDelayed({
                if (!isFinishing && (Build.VERSION.SDK_INT < Build.VERSION_CODES.JELLY_BEAN_MR1 || !isDestroyed)) {
                    enableImmersiveMode()
                }
            }, 180)
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return !isAllowedNavigation(request.url)
            }

            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                hideConnectionError()
                super.onPageStarted(view, url, favicon)
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    showConnectionError("请检查网络、服务器地址或稍后重试")
                }
                super.onReceivedError(view, request, error)
            }

            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: android.net.http.SslError) {
                // Never bypass a certificate error. The app only trusts its bundled private CA.
                handler.cancel()
                showConnectionError("安全连接验证失败，请联系管理员")
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                return try {
                    startActivityForResult(fileChooserParams.createIntent(), FILE_CHOOSER_REQUEST)
                    true
                } catch (_: Exception) {
                    fileChooserCallback = null
                    Toast.makeText(this@MainActivity, "无法打开文件选择器", Toast.LENGTH_SHORT).show()
                    false
                }
            }
        }

        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            val request = DownloadRequest(url, userAgent, contentDisposition, mimeType)
            if (!isAllowedNavigation(Uri.parse(url))) {
                Toast.makeText(this, "已拦截非本系统的下载地址", Toast.LENGTH_SHORT).show()
                return@setDownloadListener
            }
            if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
                checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
            ) {
                pendingDownload = request
                requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), STORAGE_PERMISSION_REQUEST)
            } else {
                downloadFile(request)
            }
        }
    }

    private fun isAllowedNavigation(uri: Uri): Boolean {
        if (uri.scheme.equals("blob", ignoreCase = true)) return true
        return uri.scheme.equals("https", ignoreCase = true) &&
            uri.host.equals(APP_HOST, ignoreCase = true) &&
            (uri.port == -1 || uri.port == 443)
    }

    private fun downloadFile(request: DownloadRequest) {
        Toast.makeText(this, "开始下载…", Toast.LENGTH_SHORT).show()
        downloadExecutor.execute {
            try {
                val connection = (URL(request.url).openConnection() as HttpsURLConnection).apply {
                    instanceFollowRedirects = false
                    connectTimeout = 15_000
                    readTimeout = 60_000
                    request.userAgent.takeIf { it.isNotBlank() }?.let { setRequestProperty("User-Agent", it) }
                    CookieManager.getInstance().getCookie(request.url)?.let { setRequestProperty("Cookie", it) }
                }
                connection.connect()
                if (connection.responseCode !in 200..299) {
                    throw IllegalStateException("下载响应异常：${connection.responseCode}")
                }
                val filename = URLUtil.guessFileName(
                    request.url,
                    connection.getHeaderField("Content-Disposition") ?: request.contentDisposition,
                    connection.contentType ?: request.mimeType
                ).replace(Regex("[\\\\/:*?\"<>|]"), "_")
                connection.inputStream.use { input ->
                    saveToDownloads(filename, connection.contentType ?: request.mimeType, input)
                }
                connection.disconnect()
                runOnUiThread {
                    Toast.makeText(this, "已保存到下载目录：$filename", Toast.LENGTH_LONG).show()
                }
            } catch (_: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "下载失败，请稍后重试", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun saveToDownloads(filename: String, mimeType: String?, input: java.io.InputStream) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, filename)
                put(MediaStore.Downloads.MIME_TYPE, mimeType ?: "application/octet-stream")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("无法创建下载文件")
            try {
                contentResolver.openOutputStream(uri)?.use { output -> input.copyTo(output) }
                    ?: throw IllegalStateException("无法写入下载文件")
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                contentResolver.update(uri, values, null, null)
            } catch (error: Exception) {
                contentResolver.delete(uri, null, null)
                throw error
            }
        } else {
            val directory = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!directory.exists() && !directory.mkdirs()) throw IllegalStateException("无法创建下载目录")
            FileOutputStream(File(directory, filename)).use { output -> input.copyTo(output) }
        }
    }

    private fun showConnectionError(detail: String) {
        runOnUiThread {
            errorDetail.text = detail
            errorPanel.visibility = View.VISIBLE
        }
    }

    private fun hideConnectionError() {
        if (::errorPanel.isInitialized) errorPanel.visibility = View.GONE
    }

    private fun showStartupFallback() {
        val fallback = TextView(this).apply {
            text = "应用启动异常，请更新系统 Android System WebView 后重试"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.rgb(15, 23, 42))
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
        }
        setContentView(fallback)
    }

    private fun configureFullscreenWindow() {
        try {
            window.setFlags(
                WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                window.attributes = window.attributes.apply {
                    // Allow the WebView to render behind a notch or punch hole.
                    // The web pages use safe-area insets to keep controls clear.
                    layoutInDisplayCutoutMode =
                        WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
                }
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                window.statusBarColor = Color.TRANSPARENT
                window.navigationBarColor = Color.TRANSPARENT
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.setDecorFitsSystemWindows(false)
            }
        } catch (_: RuntimeException) {
            // Fullscreen remains an enhancement on unusual OEM window managers.
        }
    }

    @Suppress("DEPRECATION")
    private fun enableImmersiveMode() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.setDecorFitsSystemWindows(false)
                window.insetsController?.apply {
                    hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                    systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            } else {
                window.decorView.systemUiVisibility =
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                        View.SYSTEM_UI_FLAG_FULLSCREEN or
                        View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                        View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                        View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
                        View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            }
        } catch (_: RuntimeException) {
            // Fullscreen is an enhancement; an OEM policy must not block app startup.
        }
    }

    @Suppress("DEPRECATION")
    private fun requestPreferredRefreshRate() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return
        try {
            val display = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) this.display else windowManager.defaultDisplay)
                ?: return
            val activeMode = display.mode
            val preferredRate = display.supportedModes
                .filter {
                    it.physicalWidth == activeMode.physicalWidth &&
                        it.physicalHeight == activeMode.physicalHeight
                }
                .maxByOrNull { it.refreshRate } ?: return
            val currentAttributes = window.attributes
            if (
                currentAttributes.preferredDisplayModeId != preferredRate.modeId ||
                currentAttributes.preferredRefreshRate != preferredRate.refreshRate
            ) {
                window.attributes = window.attributes.apply {
                    // Both fields are advisory. The mode id helps Android 9/10;
                    // the refresh-rate hint is preferred on newer Android releases.
                    preferredDisplayModeId = preferredRate.modeId
                    preferredRefreshRate = preferredRate.refreshRate
                }
            }
            Log.i(
                TAG,
                "Requested ${preferredRate.refreshRate}Hz (mode ${preferredRate.modeId}); " +
                    "active display is ${display.refreshRate}Hz"
            )
        } catch (_: RuntimeException) {
            // Keep the system-selected refresh rate on unusual display implementations.
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private data class DownloadRequest(
        val url: String,
        val userAgent: String,
        val contentDisposition: String,
        val mimeType: String
    )
}
