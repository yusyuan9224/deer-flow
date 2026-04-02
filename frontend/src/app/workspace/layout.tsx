import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuthProvider, type User } from "@/core/auth/AuthProvider";

/**
 * Server-side authentication guard for /workspace routes
 * 
 * Per RFC-001:
 * - Calls FastAPI /api/auth/me to validate session
 * - Redirects to /login if not authenticated
 * - Passes initialUser to AuthProvider to avoid client flicker
 */
export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Server-side auth check
  const user = await getAuthenticatedUser();

  // Redirect to login if not authenticated
  if (!user) {
    redirect("/login");
  }

  return (
    <AuthProvider initialUser={user}>
      <WorkspaceContent>{children}</WorkspaceContent>
    </AuthProvider>
  );
}

/**
 * Fetch current user from FastAPI
 * This runs on the server, forwarding cookies from the incoming request
 */
async function getAuthenticatedUser(): Promise<User | null> {
  try {
    // Get cookies from the incoming request
    const cookieStore = await cookies();
    const cookieHeader = cookieStore
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");

    // Get the base URL for server-side fetch
    const baseUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "http://localhost:8001";
    
    const res = await fetch(`${baseUrl}/api/auth/me`, {
      headers: {
        // Forward cookies from the incoming request
        Cookie: cookieHeader || "",
      },
      // Important: don't cache auth responses
      cache: "no-store",
    });

    if (res.ok) {
      return await res.json();
    }
    
    return null;
  } catch (error) {
    console.error("Failed to fetch authenticated user:", error);
    return null;
  }
}

/**
 * Client-side workspace content with QueryClient, sidebar, etc.
 * Separated to allow server-side auth guard in parent.
 */
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { Toaster } from "sonner";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CommandPalette } from "@/components/workspace/command-palette";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
import { getLocalSettings, useLocalSettings } from "@/core/settings";

const queryClient = new QueryClient();

function WorkspaceContent({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [settings, setSettings] = useLocalSettings();
  const [open, setOpen] = useState(false); // SSR default: open (matches server render)
  
  useLayoutEffect(() => {
    // Runs synchronously before first paint on the client — no visual flash
    setOpen(!getLocalSettings().layout.sidebar_collapsed);
  }, []);
  
  useEffect(() => {
    setOpen(!settings.layout.sidebar_collapsed);
  }, [settings.layout.sidebar_collapsed]);
  
  const handleOpenChange = useCallback(
    (open: boolean) => {
    setOpen(open);
    setSettings("layout", { sidebar_collapsed: !open });
  },
    [setSettings],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <SidebarProvider
        className="h-screen"
        open={open}
        onOpenChange={handleOpenChange}
      >
        <WorkspaceSidebar />
        <SidebarInset className="min-w-0">{children}</SidebarInset>
      </SidebarProvider>
      <CommandPalette />
      <Toaster position="top-center" />
    </QueryClientProvider>
  );
}
