import { useState } from "react";
import { api } from "../api/client";

interface ParseResult {
  file_type: string;
  period: string;
  trade_count: number;
  preview: Record<string, unknown>[];
  parse_id: string;
}

export default function ImportPage() {
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError("");
    setSuccess("");
    setParseResult(null);
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const token = (await import("../stores/auth")).useAuthStore.getState().accessToken;
      const res = await fetch("/api/v1/trades/import/parse", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Upload failed");
      }

      const data: ParseResult = await res.json();
      setParseResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm() {
    if (!parseResult) return;
    setConfirming(true);
    setError("");
    try {
      const result = await api.post<{ import_id: number; records_imported: number }>(
        "/trades/import/confirm",
        { parse_id: parseResult.parse_id },
      );
      setSuccess(`Imported ${result.records_imported} records (ID: ${result.import_id})`);
      setParseResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Import</h1>

      {/* Upload */}
      <div className="rounded-lg bg-gray-900 p-6">
        <p className="mb-3 text-sm text-gray-400">
          Upload a brokerage PDF (1099-B, 1099-DA, or monthly statement)
        </p>
        <label className="inline-block cursor-pointer rounded bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-700">
          {uploading ? "Parsing..." : "Choose PDF"}
          <input
            type="file"
            accept=".pdf"
            onChange={handleUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {success && <p className="text-sm text-green-400">{success}</p>}

      {/* Parse preview */}
      {parseResult && (
        <div className="rounded-lg bg-gray-900 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">
                {parseResult.file_type.toUpperCase()} — {parseResult.period}
              </p>
              <p className="text-sm text-gray-400">{parseResult.trade_count} trades parsed</p>
            </div>
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="rounded bg-green-600 px-4 py-2 text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {confirming ? "Importing..." : "Confirm Import"}
            </button>
          </div>

          <h3 className="text-xs text-gray-500">Preview (first 10):</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {parseResult.preview.map((row, i) => (
                  <tr key={i} className="border-t border-gray-800">
                    {Object.entries(row).map(([key, val]) => (
                      <td key={key} className="py-1.5 px-2 text-xs">
                        <span className="text-gray-500">{key}:</span>{" "}
                        {String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
