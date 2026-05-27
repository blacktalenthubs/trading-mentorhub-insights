/**
 * Capacitor iOS push notification registration hook.
 *
 * Spec 2026-05-26 — Stage 2 of mobile rollout. When the user opens the app
 * on iOS (via Capacitor native shell), we:
 *   1. Check current permission state
 *   2. Request permission if not yet decided
 *   3. Register with APNs → device token
 *   4. POST the token to the backend so it can send pushes when alerts fire
 *
 * Safe to call from any component — it no-ops on web (Capacitor.isNativePlatform()
 * returns false). Only fires real work when running inside the iOS native shell.
 *
 * Usage in App.tsx or top-level layout:
 *   usePushRegistration();
 *
 * Behavior matrix:
 *   • Web browser (PWA): no-op (Capacitor not active)
 *   • iOS native app, permission granted: registers, sends token to backend
 *   • iOS native app, permission denied: logs reason, no token sent
 *   • iOS native app, first launch: shows iOS permission prompt
 */
import { useEffect } from "react";
import { api } from "../api/client";

export function usePushRegistration() {
  useEffect(() => {
    let cancelled = false;

    async function register() {
      // Dynamic import so the web bundle doesn't crash if Capacitor isn't
      // installed yet (and so tree-shake can omit on pure-web builds).
      let Capacitor: any;
      let PushNotifications: any;
      try {
        ({ Capacitor } = await import("@capacitor/core"));
        ({ PushNotifications } = await import("@capacitor/push-notifications"));
      } catch {
        // Capacitor plugins not present — running in web. Quiet exit.
        return;
      }

      if (!Capacitor.isNativePlatform || !Capacitor.isNativePlatform()) {
        // Running in browser (PWA), not native iOS. Skip.
        return;
      }

      try {
        // Step 1: check current permission
        const perm = await PushNotifications.checkPermissions();
        let granted = perm.receive === "granted";

        // Step 2: request if not yet granted
        if (!granted && perm.receive !== "denied") {
          const result = await PushNotifications.requestPermissions();
          granted = result.receive === "granted";
        }
        if (!granted) {
          console.info("[push] permission not granted:", perm.receive);
          return;
        }

        // Step 3: listen for the APNs registration token
        PushNotifications.addListener(
          "registration",
          async (token: { value: string }) => {
            if (cancelled) return;
            try {
              await api.put("/settings/apns-token", { token: token.value });
              console.info("[push] registered with backend");
            } catch (e) {
              console.warn("[push] backend registration failed:", e);
            }
          }
        );

        PushNotifications.addListener("registrationError", (err: any) => {
          console.warn("[push] APNs registration error:", err);
        });

        // Optional: handle taps so we can deep-link into the right alert
        PushNotifications.addListener("pushNotificationActionPerformed", (notification: any) => {
          const alertId = notification?.notification?.data?.alert_id;
          if (alertId) {
            // Deep link to the trading page focused on that alert
            window.location.href = `/trading?alert=${alertId}`;
          }
        });

        // Step 4: register — triggers the APNs round-trip → 'registration' event
        await PushNotifications.register();
      } catch (e) {
        console.warn("[push] setup failed:", e);
      }
    }

    register();
    return () => { cancelled = true; };
  }, []);
}
