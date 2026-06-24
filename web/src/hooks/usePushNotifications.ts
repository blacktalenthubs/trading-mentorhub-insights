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

      // Notification tapped — route to the page that matches the notification.
      // Order: explicit route hint (agent pushes carry one) → known type →
      // a per-symbol alert → fallback to Today. Keeps every push landing where
      // its content actually lives, not a generic dashboard.
      PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
        const data = action.notification.data || {};
        if (typeof data.route === "string" && data.route.startsWith("/")) {
          navigate(data.route);                              // self-routing agent pushes
        } else if (data.type === "market_report") {
          navigate("/today?tab=reports");                    // premarket / EOD recap
        } else if (data.type === "emerging") {
          navigate("/trade-ideas?tab=emerging");             // emerging-leaders scout
        } else if (data.alert_id) {
          navigate(`/trading?alert=${encodeURIComponent(data.alert_id)}`);  // a fired alert
        } else if (data.symbol) {
          navigate(`/trading?symbol=${encodeURIComponent(data.symbol)}`);   // symbol chart (buzz, etc.)
        } else {
          navigate("/today");
        }
      });

      // Register with APNs / FCM
      await PushNotifications.register();
    })();
  }, [navigate]);
}
