/**
 * ThirdParty Access — PWA Install Prompt Handler
 * Shows a popup banner at the top of the website prompting users to install the app.
 * Works on Chrome, Edge, Samsung Internet, Opera, and other Chromium browsers (Android & Desktop).
 * Shows iOS-specific instructions for Safari users on iPhone/iPad.
 */

(function () {
  'use strict';

  // ── State ──
  let deferredPrompt = null;
  let bannerElement = null;

  // ── Detect platform ──
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isInStandaloneMode =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;

  // Don't show if already installed as PWA
  if (isInStandaloneMode) return;

  // Check if user previously dismissed (respect for 3 days)
  const dismissedAt = localStorage.getItem('pwa-install-dismissed');
  if (dismissedAt) {
    const THREE_DAYS = 3 * 24 * 60 * 60 * 1000;
    if (Date.now() - parseInt(dismissedAt, 10) < THREE_DAYS) return;
  }

  // ── Create the install banner HTML ──
  function createBanner() {
    const banner = document.createElement('div');
    banner.id = 'pwa-install-banner';
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'polite');

    // iOS gets different instructions
    const isIOSDevice = isIOS;

    banner.innerHTML = `
      <div style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 99999;
        background: #ffffff;
        color: #1e293b;
        box-shadow: 0 2px 12px rgba(0,0,0,0.12);
        border-bottom: 1px solid #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        animation: pwa-slide-down 0.4s ease-out;
      " id="pwa-banner-inner">
        <div style="
          max-width: 720px;
          margin: 0 auto;
          padding: 14px 16px;
          display: flex;
          align-items: center;
          gap: 12px;
        ">
          <!-- App Icon -->
          <img
            src="/static/icons/icon-96x96.png"
            alt="ThirdParty Access"
            style="width: 44px; height: 44px; border-radius: 10px; flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.1);"
          >

          <!-- Text -->
          <div style="flex: 1; min-width: 0;">
            <div style="font-weight: 700; font-size: 14px; line-height: 1.3; color: #1e293b;">
              Install ThirdParty Access App
            </div>
            <div style="font-size: 12px; color: #64748b; line-height: 1.3; margin-top: 2px;">
              ${isIOSDevice
                ? 'Tap <span style="font-weight:600;">Share</span> <svg style="display:inline;vertical-align:middle;width:14px;height:14px;margin:0 2px;" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2.5"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> then <span style="font-weight:600;">Add to Home Screen</span>'
                : 'Add to your home screen for quick access'
              }
            </div>
          </div>

          <!-- Action Buttons -->
          <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
            ${isIOSDevice
              ? ''
              : `<button id="pwa-install-btn" style="
                  background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
                  color: #ffffff;
                  border: none;
                  padding: 8px 18px;
                  border-radius: 8px;
                  font-weight: 700;
                  font-size: 13px;
                  cursor: pointer;
                  white-space: nowrap;
                  box-shadow: 0 2px 8px rgba(37,99,235,0.3);
                  transition: transform 0.15s ease, box-shadow 0.15s ease;
                " onmouseover="this.style.transform='scale(1.04)';this.style.boxShadow='0 4px 12px rgba(37,99,235,0.4)'"
                  onmouseout="this.style.transform='scale(1)';this.style.boxShadow='0 2px 8px rgba(37,99,235,0.3)'"
                >
                  INSTALL
                </button>`
            }
            <button id="pwa-dismiss-btn" style="
              background: transparent;
              border: none;
              color: #94a3b8;
              cursor: pointer;
              padding: 6px;
              line-height: 1;
              font-size: 20px;
              transition: color 0.15s ease;
            " onmouseover="this.style.color='#475569'" onmouseout="this.style.color='#94a3b8'"
              aria-label="Dismiss install prompt"
            >&times;</button>
          </div>
        </div>
      </div>
    `;

    // Add animation keyframe
    const style = document.createElement('style');
    style.textContent = `
      @keyframes pwa-slide-down {
        from { transform: translateY(-100%); opacity: 0; }
        to   { transform: translateY(0); opacity: 1; }
      }
      @keyframes pwa-slide-up {
        from { transform: translateY(0); opacity: 1; }
        to   { transform: translateY(-100%); opacity: 0; }
      }
      /* Push page content down when banner is visible */
      body.pwa-banner-visible {
        padding-top: 72px !important;
      }
      @media (max-width: 480px) {
        body.pwa-banner-visible {
          padding-top: 80px !important;
        }
      }
    `;
    document.head.appendChild(style);

    return banner;
  }

  // ── Show the banner ──
  function showBanner() {
    if (bannerElement) return; // Already shown
    bannerElement = createBanner();
    document.body.prepend(bannerElement);
    document.body.classList.add('pwa-banner-visible');

    // Wire up dismiss
    const dismissBtn = document.getElementById('pwa-dismiss-btn');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', dismissBanner);
    }

    // Wire up install (Android/Desktop Chrome)
    const installBtn = document.getElementById('pwa-install-btn');
    if (installBtn) {
      installBtn.addEventListener('click', triggerInstall);
    }
  }

  // ── Dismiss the banner ──
  function dismissBanner() {
    if (!bannerElement) return;
    const inner = document.getElementById('pwa-banner-inner');
    if (inner) {
      inner.style.animation = 'pwa-slide-up 0.3s ease-in forwards';
      setTimeout(() => {
        if (bannerElement && bannerElement.parentNode) {
          bannerElement.parentNode.removeChild(bannerElement);
        }
        bannerElement = null;
        document.body.classList.remove('pwa-banner-visible');
      }, 300);
    } else {
      if (bannerElement.parentNode) bannerElement.parentNode.removeChild(bannerElement);
      bannerElement = null;
      document.body.classList.remove('pwa-banner-visible');
    }
    localStorage.setItem('pwa-install-dismissed', Date.now().toString());
  }

  // ── Trigger the native install prompt ──
  async function triggerInstall() {
    if (!deferredPrompt) return;

    // Show the native browser install dialog
    deferredPrompt.prompt();

    const result = await deferredPrompt.userChoice;
    if (result.outcome === 'accepted') {
      console.log('ThirdParty Access: App installed successfully');
    } else {
      console.log('ThirdParty Access: Install dismissed by user');
    }

    deferredPrompt = null;
    dismissBanner();
  }

  // ══════════════════════════════════════════════════════════════
  //  EVENT LISTENERS
  // ══════════════════════════════════════════════════════════════

  // Chromium browsers fire 'beforeinstallprompt' when criteria are met
  window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the default mini-infobar
    e.preventDefault();
    // Stash the event so we can trigger it later
    deferredPrompt = e;
    // Show our custom banner
    showBanner();
  });

  // If the app gets installed, hide the banner
  window.addEventListener('appinstalled', () => {
    console.log('ThirdParty Access: App was installed');
    deferredPrompt = null;
    dismissBanner();
    localStorage.removeItem('pwa-install-dismissed');
  });

  // For iOS: show the banner after a short delay (iOS doesn't fire beforeinstallprompt)
  if (isIOS && !isInStandaloneMode) {
    setTimeout(() => {
      showBanner();
    }, 2000);
  }

})();
