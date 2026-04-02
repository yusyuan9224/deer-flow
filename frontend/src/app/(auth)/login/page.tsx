"use client";

import { useRouter, from "next/navigation";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/core/auth/AuthProvider";
import { fetchWithAuth } from "@/core/api/fetcher";

/**
 * Validate next parameter
 * Prevent open redirect attacks
 * Per RFC-001: Only allow relative paths starting with /
 */
function validateNextParam(next: string | null): string | null {
  if (!next) {
    return null;
  }
  
  // Need start with / (relative path)
  if (!next.startsWith("/")) {
    return null;
  }
  
  // Disallow protocol-relative URLs
  if (next.startsWith("//") || next.startsWith("http://") || next.startsWith("https://")) {
    return null;
  }
  
  // Disallow URLs with different protocols (e.g., javascript:, data:, etc)
  if (next.includes(":") && !next.startsWith("/")) {
    return null;
  }
  
  // Valid relative path
  return next;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isAuthenticated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLogin, setIsLogin] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Get next parameter for validated redirect
  const nextParam = searchParams.get("next");
  const redirectPath = validateNextParam(nextParam) || "/workspace";

  // Redirect if already authenticated
  if (isAuthenticated) {
    router.push(redirectPath);
    return;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const endpoint = isLogin ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body = isLogin
        ? `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
        : JSON.stringify({ email, password });

      const headers: HeadersInit = isLogin
        ? { "Content-Type": "application/x-www-form-urlencoded" }
        : { "Content-Type": "application/json" };

      const res = await fetch(endpoint, {
        method: "POST",
        headers,
        body,
        credentials: "include", // Important: include HttpOnly cookie
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "Authentication failed");
        return;
      }

      if (isLogin) {
        // Login successful,        // Redirect to next or workspace
        router.push(redirectPath);
      } else {
        // Registration successful, switch to login mode
        setIsLogin(true);
        setError("");
        alert("Registration successful! Please login.");
      }
    } catch (err) {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a]">
      <div className="w-full max-w-md space-y-6 rounded-lg border border-border/20 bg-black/50 p-8 backdrop-blur-sm">
        <div className="text-center">
          <h1 className="font-serif text-3xl">DeerFlow</h1>
          <p className="mt-2 text-muted-foreground">
            {isLogin ? "Sign in to your account" : "Create a new account"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="mt-1 bg-white text-black"
            />
          </div>

          <div>
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="•••••••"
              required
              minLength={isLogin ? 6 : 8}
              className="mt-1 bg-white text-black"
            />
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Please wait..." : isLogin ? "Sign In" : "Create Account"}
          </Button>
        </form>

        <div className="text-center text-sm">
          <button
            type="button"
            onClick={() => {
              setIsLogin(!isLogin);
              setError("");
            }}
            className="text-blue-500 hover:underline"
          >
            {isLogin
              ? "Don't have an account? Sign up"
              : "Already have an account? Sign in"}
          </button>
        </div>

        <div className="text-center text-xs text-muted-foreground">
          <a href="/" className="hover:underline">
            ← Back to home
          </a>
        </div>
      </div>
    </div>
  );
}
