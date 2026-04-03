/**
 * Push notification setup for native iOS/Android.
 *
 * - Requests permission on mount (native only)
 * - Registers device token with the backend
 * - Handles tap-to-navigate (deep link to dashboard on alert tap)
 *
 * No-op on web — SSE (useAlertStream) handles real-time there.
 */

import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Capacitor } from "@capacitor/core";
import { api } from "../api/client";

export function usePushNotifications() {
  const navigate = useNavigate();
  const registeredRef = useRef(false);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || registeredRef.current) return;
    registeredRef.current = true;

    (async () => {
      const { PushNotifications } = await import("@capacitor/push-notifications");

      // Check / request permission
      let perm = await PushNotifications.checkPermissions();
      if (perm.receive === "prompt") {
        perm = await PushNotifications.requestPermissions();
      }
      if (perm.receive !== "granted") {
        console.warn("Push notification permission denied");
        return;
      }

      // Listen for registration success — send token to backend
      PushNotifications.addListener("registration", async (token) => {
        try {
          await api.post("/push/register", {
            token: token.value,
            platform: Capacitor.getPlatform(), // "ios" or "android"
          });
        } catch (err) {
          console.error("Failed to register push token", err);
        }
      });

      // Registration error
      PushNotifications.addListener("registrationError", (err) => {
        console.error("Push registration error:", err);
      });

      // Notification received while app is in foreground — already handled by SSE
      // so we only log it here for debugging
      PushNotifications.addListener("pushNotificationReceived", (notification) => {
        console.log("Push received (foreground):", notification);
      });

      // Notification tapped — navigate to dashboard
      PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
        const data = action.notification.data;
        if (data?.symbol) {
          // Navigate to charts page with the symbol pre-selected
          navigate(`/charts?symbol=${encodeURIComponent(data.symbol)}`);
        } else {
          navigate("/");
        }
      });

      // Register with APNs / FCM
      await PushNotifications.register();
    })();
  }, [navigate]);
}
