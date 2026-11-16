# supabase/

```bash
supabase login
supabase link --project-ref <your-project-ref>
supabase db push                # applies migrations/
```

Then in the dashboard:

1. **Authentication → Providers**: enable *Email* (magic link; disable "Confirm email" if you want
   one-click sign-in) and *Google* (paste the OAuth client id/secret from Google Cloud Console).
2. **Authentication → URL configuration**: Site URL = your web URL; add
   `http://localhost:3000/auth/callback` and `https://<your-domain>/auth/callback` to Redirect URLs.
3. **Project Settings → API**: copy the anon key (web), service role key (API) and JWT secret (API).

Tables: `profiles`, `plans`, `plan_steps`, `usage_events`, `previews`, `leads`. RLS is enabled on
every table; the API writes with the service role and scopes every query by `user_id`.

## Auth email: links that work in any browser

Sign-in emails must work when the link is opened somewhere other than the browser that asked for it
(another device, a mail app's in-app browser). Two flows make that true:

1. **Token-hash links (preferred).** `supabase/templates/magic_link.html` and `confirm_signup.html`
   link to `<site>/auth/callback?token_hash={{ .TokenHash }}&type=email&redirect_to={{ .RedirectTo }}`
   and print the one-time code (`{{ .Token }}`). The callback verifies the hash server-side with
   `verifyOtp`, and the login page accepts the code as a fallback. Supabase only lets free-tier
   projects customise templates once a custom SMTP sender exists, so apply both in one go:

   ```bash
   RESEND_API_KEY=re_… AUTH_FROM_EMAIL='Permit Memo <auth@your-domain>' supabase/push-auth-templates.sh
   ```

   `AUTH_FROM_EMAIL` is required and must be on a domain verified in Resend.

2. **Default template (until SMTP is configured).** Magic links are *requested* through a plain
   implicit-flow client (`getSupabaseOtpClient`; `@supabase/ssr` pins PKCE, whose code verifier only
   exists in the requesting browser). Supabase verifies the default `{{ .ConfirmationURL }}` link
   itself and lands on `/auth/callback` with the session in the URL fragment; the callback forwards to
   `/auth/complete`, which calls `setSession` on the cookie-backed client. No verifier is involved, so
   the link works cross-browser. The default template carries no code, so the code input only becomes
   useful after step 1.
