/** Platform-specific setup — status bar, splash screen hide, haptic feedback. */

import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";

export function useNativePlatform() {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    (async () => {
      // Hide splash screen after the React tree has mounted
      const { SplashScreen } = await import("@capacitor/splash-screen");
      await SplashScreen.hide();

      // Dark status bar (light text on dark bg)
      const { StatusBar, Style } = await import("@capacitor/status-bar");
      await StatusBar.setStyle({ style: Style.Dark });
    })();
  }, []);
}

/** Fire a light haptic tap — no-op on web. */
export async function hapticTap() {
  if (!Capacitor.isNativePlatform()) return;
  const { Haptics, ImpactStyle } = await import("@capacitor/haptics");
  await Haptics.impact({ style: ImpactStyle.Light });
}
