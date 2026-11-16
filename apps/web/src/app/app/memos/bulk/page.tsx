import type { Metadata } from "next";
import { BulkUpload } from "@/components/memo/bulk-upload";

export const metadata: Metadata = { title: "Bulk upload" };

export default function BulkUploadPage() {
  return <BulkUpload />;
}
