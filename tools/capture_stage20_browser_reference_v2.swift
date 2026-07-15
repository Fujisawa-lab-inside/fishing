import AppKit
import Foundation
import WebKit

@MainActor
final class CaptureController: NSObject, WKNavigationDelegate {
    private let application: NSApplication
    private let window: NSWindow
    private let webView: WKWebView
    private let screenshotURL: URL
    private let resultURL: URL
    private var attempts = 0

    init(application: NSApplication, pageURL: URL, screenshotURL: URL, resultURL: URL) {
        self.application = application
        self.screenshotURL = screenshotURL
        self.resultURL = resultURL
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        self.webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 1000, height: 820), configuration: configuration)
        self.window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1000, height: 820),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        super.init()
        self.window.contentView = self.webView
        self.webView.navigationDelegate = self
        self.window.orderFrontRegardless()
        self.webView.load(URLRequest(url: pageURL))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        webView.evaluateJavaScript("document.querySelector('#run').click()") { [weak self] _, error in
            if let error {
                self?.finishWithError("click failed: \(error)")
                return
            }
            self?.poll()
        }
    }

    private func poll() {
        attempts += 1
        if attempts > 300 {
            finishWithError("page validation timed out")
            return
        }
        let script = """
        (() => {
          const status = document.querySelector('#status');
          const result = document.querySelector('#result');
          return {
            state: status.dataset.state || '',
            status: status.textContent,
            resultHidden: result.hidden,
            version: document.querySelector('#version').textContent,
            mesh: document.querySelector('#mesh').textContent,
            wasm: document.querySelector('#wasm').textContent,
            velocity: document.querySelector('#velocity').textContent,
            depth: document.querySelector('#depth').textContent,
            timestep: document.querySelector('#timestep').textContent,
            time: document.querySelector('#time').textContent,
            title: document.title,
            url: location.href
          };
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("poll failed: \(error)")
                return
            }
            guard let record = value as? [String: Any] else {
                self.finishWithError("unexpected page result")
                return
            }
            if record["state"] as? String == "passed", record["resultHidden"] as? Bool == false {
                self.capture(record: record)
                return
            }
            if record["state"] as? String == "failed" {
                self.finishWithError(record["status"] as? String ?? "page validation failed")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { self.poll() }
        }
    }

    private func capture(record: [String: Any]) {
        let configuration = WKSnapshotConfiguration()
        configuration.rect = webView.bounds
        webView.takeSnapshot(with: configuration) { [weak self] image, error in
            guard let self else { return }
            if let error {
                self.finishWithError("snapshot failed: \(error)")
                return
            }
            guard let image,
                  let tiff = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiff),
                  let png = bitmap.representation(using: .png, properties: [:]) else {
                self.finishWithError("snapshot encoding failed")
                return
            }
            do {
                try png.write(to: self.screenshotURL)
                var output = record
                output["browserEngine"] = "WKWebView/WebKit"
                output["screenshot"] = self.screenshotURL.path
                output["capturedAt"] = ISO8601DateFormatter().string(from: Date())
                let json = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
                try json.write(to: self.resultURL)
                print(String(data: json, encoding: .utf8) ?? "{}")
                self.application.terminate(nil)
            } catch {
                self.finishWithError("write failed: \(error)")
            }
        }
    }

    private func finishWithError(_ message: String) {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        application.terminate(nil)
        exit(1)
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 4,
      let pageURL = URL(string: arguments[1]) else {
    FileHandle.standardError.write(Data("usage: capture_stage20_browser_reference_v2.swift PAGE_URL SCREENSHOT RESULT_JSON\n".utf8))
    exit(2)
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let controller = MainActor.assumeIsolated {
    CaptureController(
        application: application,
        pageURL: pageURL,
        screenshotURL: URL(fileURLWithPath: arguments[2]),
        resultURL: URL(fileURLWithPath: arguments[3])
    )
}
withExtendedLifetime(controller) {
    application.run()
}
