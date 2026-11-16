"use client";

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { Button } from "@/components/ui/button";
import { api, describeApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";

export function ExportPdfButton({ planId, title, version }: { planId: string; title: string; version: number }) {
  const { accessToken } = useApp();
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      const blob = await api.exportPdf(accessToken, planId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "plan";
      a.href = url;
      a.download = `permit-memo-${slug}-v${version}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      capture("pdf_exported", { plan_id: planId, version });
    } catch (err) {
      toast.error("Export failed", { description: describeApiError(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button type="button" variant="outline" onClick={download} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : <FileDown />}
      Export PDF
    </Button>
  );
}
