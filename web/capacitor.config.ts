import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.aicopilottrader.app",
  appName: "TradeSignal",
  webDir: "dist",
  server: {
    // Load from production so mobile + web stay in lockstep with every Railway
    // deploy. Without this, the iOS app freezes on whatever dist/ was bundled
    // at the last Xcode build. For local dev, swap to http://YOUR_LOCAL_IP:5173.
    url: "https://www.busytradersdesk.com",
    androidScheme: "https",
    iosScheme: "https",
    cleartext: false,
  },
  plugins: {
    SplashScreen: {
      launchAutoHide: true,
      launchShowDuration: 1500,
      backgroundColor: "#0a0a0f",
      showSpinner: false,
    },
    StatusBar: {
      style: "DARK",
      backgroundColor: "#0a0a0f",
    },
  },
};

export default config;
