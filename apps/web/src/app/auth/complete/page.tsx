import { Suspense } from "react";
import { CompleteSignIn } from "@/components/auth/complete-sign-in";

export const metadata = { title: "Signing you in" };

export default function AuthCompletePage() {
  return (
    <main className="mx-auto flex min-h-[60vh] w-full max-w-md items-center px-4">
      <Suspense fallback={null}>
        <CompleteSignIn />
      </Suspense>
    </main>
  );
}
