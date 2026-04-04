import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.aicopilottrader.app",
  appName: "TradeSignal",
  webDir: "dist",
  server: {
    // In production, the app loads from the built bundle (no server needed).
    // During dev you can uncomment the url below to live-reload from Vite:
    // url: "http://YOUR_LOCAL_IP:5173",
    androidScheme: "https",
    iosScheme: "https",
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
