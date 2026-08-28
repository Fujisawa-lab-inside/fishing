import AppKit
import Foundation
import WebKit

@MainActor
final class HybridGuiCaptureController: NSObject, WKNavigationDelegate {
    private let application: NSApplication
    private let window: NSWindow
    private let webView: WKWebView
    private let screenshotURL: URL
    private let resultURL: URL
    private let scrollTarget: String?
    private var attempts = 0
    private var sawRuntimeAlert = false

    init(
        application: NSApplication,
        pageURL: URL,
        screenshotURL: URL,
        resultURL: URL,
        width: Int,
        height: Int,
        scrollTarget: String?
    ) {
        self.application = application
        self.screenshotURL = screenshotURL
        self.resultURL = resultURL
        self.scrollTarget = scrollTarget
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.preferences.setValue(true, forKey: "developerExtrasEnabled")
        self.webView = WKWebView(
            frame: NSRect(x: 0, y: 0, width: width, height: height),
            configuration: configuration
        )
        self.window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
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
        poll()
    }

    private func poll() {
        attempts += 1
        if attempts > 600 {
            finishWithError("GUI readiness timed out")
            return
        }
        let script = """
        (() => {
          const app = document.querySelector('#app-shell');
          const alert = document.querySelector('#runtime-version-alert');
          const workspace = document.querySelector('#workspace');
          return {
          phase: app?.dataset.phase || '',
          freshness: app?.dataset.runtimeFreshness || '',
          expectedContract: app?.dataset.browserContractVersion || '',
          activeContract: app?.dataset.activeBrowserContractVersion || '',
          alertVisible: Boolean(alert && !alert.hidden),
          workspaceInert: Boolean(workspace?.inert),
          overlay: document.querySelector('#overlay-message')?.textContent || '',
          title: document.title
          };
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("readiness poll failed: \(error)")
                return
            }
            guard let record = value as? [String: Any] else {
                self.finishWithError("unexpected readiness result")
                return
            }
            if record["alertVisible"] as? Bool == true {
                self.sawRuntimeAlert = true
            }
            let contractMatches = record["expectedContract"] as? String == "m0.2-ui-20260826-01"
                && record["activeContract"] as? String == record["expectedContract"] as? String
            if record["phase"] as? String == "ready",
               record["freshness"] as? String == "current",
               contractMatches,
               record["alertVisible"] as? Bool == false,
               record["workspaceInert"] as? Bool == false {
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    self.exerciseInterface()
                }
                return
            }
            if record["phase"] as? String == "error" {
                self.finishWithError(record["overlay"] as? String ?? "GUI load failed")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                self.poll()
            }
        }
    }

    private func exerciseInterface() {
        let script = """
        (() => {
          const gateButtons = [...document.querySelectorAll('[data-gate]')];
          const initiallyAutomatic = document.querySelector('#gate-summary-badge').textContent.trim() === '自動推定・段階8/8'
            && gateButtons.every(button => button.getAttribute('aria-pressed') === 'true');
          const fieldValuesBefore = ['metric-speed', 'metric-barrage', 'timeline-current']
            .map(id => document.querySelector(`#${id}`).textContent.trim()).join('|');
          document.querySelector('#gate-mode-field').click();
          document.querySelector('[data-gate-preset="closed"]').click();
          for (const gate of ['0', '3', '7']) document.querySelector(`[data-gate="${gate}"]`).click();
          const gateInputWorked = gateButtons
            .filter(button => button.getAttribute('aria-pressed') === 'true')
            .map(button => Number(button.dataset.gate) + 1)
            .join(',') === '1,4,8';
          const fieldValuesAfter = ['metric-speed', 'metric-barrage', 'timeline-current']
            .map(id => document.querySelector(`#${id}`).textContent.trim()).join('|');
          const fieldValuesUnchanged = fieldValuesBefore === fieldValuesAfter;
          document.documentElement.dataset.gateFieldsUnchanged = String(fieldValuesUnchanged);
          document.querySelector('[data-view="barrage"]').click();
          document.querySelector('[data-layer="depth"]').click();
          const slider = document.querySelector('#time-slider');
          slider.value = '35';
          slider.dispatchEvent(new Event('input', { bubbles: true }));
          document.querySelector('#play-button').click();
          return initiallyAutomatic && gateInputWorked && fieldValuesUnchanged;
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("GUI setup interaction failed: \(error)")
                return
            }
            guard value as? Bool == true else {
                self.finishWithError("GUI gate input did not transition from automatic stage 8 to field gates 1,4,8 open")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                self.verifyPlaybackEndpoint()
            }
        }
    }

    private func verifyPlaybackEndpoint() {
        let script = """
        (() => {
          const timeline = document.querySelector('#timeline-current');
          const play = document.querySelector('#play-button');
          const playLabel = document.querySelector('#play-label');
          const reachedEndpoint = timeline.textContent.trim() === '+24時間'
            && playLabel.textContent.trim() === '再生'
            && !play.classList.contains('playing');
          play.click();
          const stayedAtEndpoint = timeline.textContent.trim() === '+24時間'
            && playLabel.textContent.trim() === '再生'
            && !play.classList.contains('playing');
          const slider = document.querySelector('#time-slider');
          slider.value = '18';
          slider.dispatchEvent(new Event('input', { bubbles: true }));
          return reachedEndpoint && stayedAtEndpoint;
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("GUI playback endpoint check failed: \(error)")
                return
            }
            guard value as? Bool == true else {
                self.finishWithError("GUI playback did not stop at +24 hours")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.selectPoint()
            }
        }
    }

    private func selectPoint() {
        let script = """
        (() => {
          const canvas = document.querySelector('#flow-map');
          const rect = canvas.getBoundingClientRect();
          canvas.focus();
          canvas.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
          if (document.querySelector('#selected-cell-id').textContent.trim() !== '未選択') {
            canvas.dataset.captureSelectionMethod = 'keyboard';
            return true;
          }
          const probe = (x, y) => {
            canvas.dispatchEvent(new MouseEvent('click', {
              bubbles: true,
              clientX: rect.left + x,
              clientY: rect.top + y
            }));
            return document.querySelector('#selected-cell-id').textContent.trim() !== '未選択';
          };
          const preferred = [
            [rect.width * 0.5, rect.height * 0.5],
            [rect.width * 0.4, rect.height * 0.5],
            [rect.width * 0.6, rect.height * 0.5]
          ];
          for (const [x, y] of preferred) {
            if (probe(x, y)) {
              canvas.dataset.captureSelectionMethod = 'pointer';
              return true;
            }
          }
          for (let y = 24; y < rect.height; y += 36) {
            for (let x = 24; x < rect.width; x += 36) {
              if (probe(x, y)) {
                canvas.dataset.captureSelectionMethod = 'pointer';
                return true;
              }
            }
          }
          return false;
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("GUI point interaction failed: \(error)")
                return
            }
            guard value as? Bool == true else {
                self.finishWithError("GUI point interaction did not select a cell")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                self.readInterface()
            }
        }
    }

    private func readInterface() {
        let script = """
        (() => {
          const canvas = document.querySelector('#flow-map');
          const rect = canvas.getBoundingClientRect();
          const activeView = document.querySelector('[data-view].active');
          const activeLayer = document.querySelector('[data-layer].active');
          const sourceBadge = document.querySelector('.source-badge');
          const warning = document.querySelector('#warning-hud');
          const calculationBanner = document.querySelector('#local-calculation-banner');
          const calculationJump = document.querySelector('#local-calculation-jump');
          const app = document.querySelector('#app-shell');
          const runtimeAlert = document.querySelector('#runtime-version-alert');
          const slider = document.querySelector('#time-slider');
          const workspace = document.querySelector('#workspace');
          const controlPanel = document.querySelector('#control-panel');
          const mapSection = document.querySelector('#map-section');
          const gateButtons = [...document.querySelectorAll('[data-gate]')];
          const gateContract = document.querySelector('.gate-contract');
          const mobile = matchMedia('(max-width: 760px)').matches;
          const isVisible = element => {
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
          };
          const controlOrder = Number.parseInt(getComputedStyle(controlPanel).order, 10) || 0;
          const mapOrder = Number.parseInt(getComputedStyle(mapSection).order, 10) || 0;
          return {
            phase: app.dataset.phase,
            runtimeFreshness: app.dataset.runtimeFreshness,
            expectedBrowserContract: app.dataset.browserContractVersion,
            activeBrowserContract: app.dataset.activeBrowserContractVersion,
            runtimeAlertVisible: isVisible(runtimeAlert),
            workspaceInert: Boolean(workspace.inert),
            title: document.title,
            activeView: activeView?.textContent.trim(),
            activeViewId: activeView?.dataset.view,
            activeLayer: activeLayer?.textContent.trim(),
            activeLayerId: activeLayer?.dataset.layer,
            timeline: document.querySelector('#timeline-current').textContent.trim(),
            sliderAriaValueText: slider.getAttribute('aria-valuetext'),
            frameCount: document.querySelector('#frame-count').textContent.trim(),
            selectedCell: document.querySelector('#selected-cell-id').textContent.trim(),
            selectionMethod: canvas.dataset.captureSelectionMethod || '',
            gateCount: gateButtons.length,
            openGates: gateButtons.filter(button => button.getAttribute('aria-pressed') === 'true').map(button => Number(button.dataset.gate) + 1).join(','),
            gateSummary: document.querySelector('#gate-summary-badge').textContent.trim(),
            gateContract: gateContract.textContent.replace(/\\s+/g, ' ').trim(),
            gateContractVisible: isVisible(gateContract),
            mapGateLabel: document.querySelector('#map-gate-label').textContent.trim(),
            gateFieldsUnchanged: document.documentElement.dataset.gateFieldsUnchanged === 'true',
            gatePositionSource: canvas.dataset.gatePositionSource || '',
            gateModelOpeningWidthMetres: canvas.dataset.gateModelOpeningWidthMetres || '',
            fishwaySeparated: canvas.dataset.fishwaySeparated === 'true',
            canvasWidth: Math.round(rect.width),
            canvasHeight: Math.round(rect.height),
            canvasAria: canvas.getAttribute('aria-label'),
            demoBadge: document.querySelector('.demo-badge').textContent.trim(),
            sourceBadge: sourceBadge.textContent.trim(),
            sourceBadgeVisible: isVisible(sourceBadge),
            warning: warning.textContent.replace(/\\s+/g, ' ').trim(),
            warningVisible: isVisible(warning),
            calculationStatus: calculationBanner.dataset.status,
            calculationTitle: document.querySelector('#local-calculation-title').textContent.trim(),
            calculationNote: document.querySelector('#local-calculation-note').textContent.trim(),
            calculationBannerVisible: isVisible(calculationBanner),
            calculationJumpVisible: isVisible(calculationJump),
            mobile,
            documentOrderMatchesVisual: mobile ? mapOrder < controlOrder : controlOrder <= mapOrder,
            viewCount: document.querySelectorAll('[data-view]').length,
            layerCount: document.querySelectorAll('[data-layer]').length,
            horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth
          };
        })()
        """
        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                self.finishWithError("GUI interaction failed: \(error)")
                return
            }
            guard var record = value as? [String: Any] else {
                self.finishWithError("unexpected GUI interaction result")
                return
            }
            guard record["phase"] as? String == "ready",
                  record["runtimeFreshness"] as? String == "current",
                  record["expectedBrowserContract"] as? String == "m0.2-ui-20260826-01",
                  record["activeBrowserContract"] as? String == record["expectedBrowserContract"] as? String,
                  record["runtimeAlertVisible"] as? Bool == false,
                  record["workspaceInert"] as? Bool == false,
                  self.sawRuntimeAlert == false,
                  record["viewCount"] as? Int == 4,
                  record["layerCount"] as? Int == 3,
                  record["activeViewId"] as? String == "barrage",
                  record["activeLayerId"] as? String == "depth",
                  record["timeline"] as? String == "+6時間",
                  record["sliderAriaValueText"] as? String == "6時間後",
                  record["selectedCell"] as? String != "未選択",
                  record["selectionMethod"] as? String == "keyboard",
                  record["gateCount"] as? Int == 8,
                  record["openGates"] as? String == "1,4,8",
                  record["gateSummary"] as? String == "現地・標準順序外",
                  (record["gateContract"] as? String)?.contains("8門入力・R1Cローカル計算") == true,
                  (record["gateContract"] as? String)?.contains("入力を流れ図へ反映") == true,
                  record["gateContractVisible"] as? Bool == true,
                  (record["mapGateLabel"] as? String)?.contains("現地入力：標準順序外") == true,
                  (record["mapGateLabel"] as? String)?.contains("実行ボタンで水門状態だけR1C物理計算へ反映") == true,
                  record["gateFieldsUnchanged"] as? Bool == true,
                  record["gatePositionSource"] as? String == "gate-reference-anchor-authority-v2",
                  record["gateModelOpeningWidthMetres"] as? String == "46.5",
                  record["fishwaySeparated"] as? Bool == true,
                  (record["canvasAria"] as? String)?.contains("A1〜A8は水門番号の参照アンカー") == true,
                  (record["canvasAria"] as? String)?.contains("魚道は主水門1〜8とは別") == true,
                  (record["sourceBadge"] as? String)?.contains("合成データ") == true,
                  record["sourceBadgeVisible"] as? Bool == !((record["mobile"] as? Bool) ?? false),
                  (record["warning"] as? String)?.contains("合成データ（物理計算未実行・予測ではありません）") == true,
                  record["warningVisible"] as? Bool == true,
                  record["calculationStatus"] as? String == "not-run",
                  record["calculationTitle"] as? String == "ローカル計算：未実行",
                  (record["calculationNote"] as? String)?.contains("計算は明示操作後に開始します") == true,
                  record["calculationBannerVisible"] as? Bool == true,
                  record["calculationJumpVisible"] as? Bool == true,
                  record["documentOrderMatchesVisual"] as? Bool == true,
                  (record["canvasWidth"] as? Int ?? 0) >= 280,
                  (record["canvasHeight"] as? Int ?? 0) >= 320,
                  record["horizontalOverflow"] as? Bool == false else {
                self.finishWithError("GUI acceptance condition failed: \(record)")
                return
            }
            record["browserEngine"] = "WKWebView/WebKit"
            record["capturedAt"] = ISO8601DateFormatter().string(from: Date())
            record["screenshot"] = screenshotURL.path
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                self.prepareCapture(record: record)
            }
        }
    }

    private func prepareCapture(record: [String: Any]) {
        guard scrollTarget == "gate" else {
            capture(record: record)
            return
        }
        webView.evaluateJavaScript("document.querySelector('#gate-input-card').scrollIntoView({ block: 'start' }); true") { [weak self] _, error in
            guard let self else { return }
            if let error {
                self.finishWithError("GUI gate-card scroll failed: \(error)")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.capture(record: record)
            }
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
                let json = try JSONSerialization.data(
                    withJSONObject: record,
                    options: [.prettyPrinted, .sortedKeys]
                )
                try json.write(to: self.resultURL)
                print(String(data: json, encoding: .utf8) ?? "{}")
                self.application.terminate(nil)
            } catch {
                self.finishWithError("capture write failed: \(error)")
            }
        }
    }

    private func finishWithError(_ message: String) {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        exit(1)
    }
}

let arguments = CommandLine.arguments
guard (arguments.count == 6 || arguments.count == 7),
      let pageURL = URL(string: arguments[1]),
      let width = Int(arguments[4]),
      let height = Int(arguments[5]) else {
    FileHandle.standardError.write(
        Data("usage: capture_stage20_hybrid_gui.swift PAGE_URL SCREENSHOT RESULT_JSON WIDTH HEIGHT [gate]\n".utf8)
    )
    exit(2)
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
let controller = MainActor.assumeIsolated {
    HybridGuiCaptureController(
        application: application,
        pageURL: pageURL,
        screenshotURL: URL(fileURLWithPath: arguments[2]),
        resultURL: URL(fileURLWithPath: arguments[3]),
        width: width,
        height: height,
        scrollTarget: arguments.count == 7 ? arguments[6] : nil
    )
}
withExtendedLifetime(controller) {
    application.run()
}
