"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PublicHeader } from "@/components/public-header";
import { useMutation, useQuery } from "@tanstack/react-query";
import { authApi } from "@/lib/api";
import { formatApiError } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AlertCircle, Loader2, ShieldCheck } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [error, setError] = useState("");

  // Spec 0019: the first account of an installation without root becomes root
  const setupQuery = useQuery({ queryKey: ["auth-setup"], queryFn: authApi.setupStatus, retry: 1 });
  const creatingRoot = setupQuery.data?.root_pending === true;
  const tokenRequired = creatingRoot && setupQuery.data?.setup_token_required === true;
  // Setup state unknown (request failed): offer the token field, optional, so a root
  // registration in production is still possible
  const tokenOffered = tokenRequired || setupQuery.isError;
  const [success, setSuccess] = useState(false);
  const [createdRoot, setCreatedRoot] = useState(false);

  const registerMutation = useMutation({
    mutationFn: authApi.register,
    onSuccess: (user) => {
      setCreatedRoot(user.is_root === true);
      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 2000);
    },
    onError: (error: any) => {
      setError(formatApiError(error));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    registerMutation.mutate({
      email,
      username,
      password,
      ...(tokenOffered && setupToken ? { setup_token: setupToken } : {}),
    });
  };

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background to-muted">
        <PublicHeader />
        <main className="flex min-h-[calc(100vh-72px)] items-center justify-center p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="text-center text-2xl">Success!</CardTitle>
              <CardDescription className="text-center">
                {createdRoot
                  ? "Your root account has been created. Sign in to open the admin console. Redirecting to login..."
                  : "Your account has been created. Redirecting to login..."}
              </CardDescription>
            </CardHeader>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted">
      <PublicHeader />
      <main className="flex min-h-[calc(100vh-72px)] items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-3xl font-bold text-center">
              {creatingRoot ? "Create the root account" : "Create an Account"}
            </CardTitle>
            <CardDescription className="text-center">
              {creatingRoot
                ? "This installation has no users yet. This first account becomes root: the platform administrator, who cannot be removed or demoted."
                : "Start converting your documents to Markdown"}
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4">
              {error && (
                <div className="rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive flex items-start gap-2 animate-in slide-in-from-top-2">
                  <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="font-medium">Registration Failed</p>
                    <p className="text-xs mt-1 opacity-90">{error}</p>
                  </div>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter your email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (error) setError("");
                  }}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Choose a username"
                  value={username}
                  onChange={(e) => {
                    setUsername(e.target.value);
                    if (error) setError("");
                  }}
                  required
                  minLength={3}
                  maxLength={50}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Create a password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (error) setError("");
                  }}
                  required
                  minLength={6}
                />
                <p className="text-xs text-muted-foreground">
                  Password must be at least 6 characters long
                </p>
              </div>
              {tokenOffered && (
                <div className="space-y-2">
                  <Label htmlFor="setup-token" className="flex items-center gap-1.5">
                    <ShieldCheck className="h-4 w-4" />
                    Setup token
                  </Label>
                  <Input
                    id="setup-token"
                    type="password"
                    autoComplete="off"
                    placeholder="ROOT_SETUP_TOKEN from the server"
                    value={setupToken}
                    onChange={(e) => {
                      setSetupToken(e.target.value);
                      if (error) setError("");
                    }}
                    required={tokenRequired}
                    maxLength={256}
                  />
                  <p className="text-xs text-muted-foreground">
                    {tokenRequired
                      ? "Ask whoever deployed this server for the value of ROOT_SETUP_TOKEN."
                      : "Only needed if this is the first account of a new installation."}
                  </p>
                </div>
              )}
            </CardContent>
            <CardFooter className="flex flex-col space-y-4">
              <Button
                type="submit"
                className="w-full"
                disabled={registerMutation.isPending || setupQuery.isLoading}
              >
                {registerMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating account...
                  </>
                ) : creatingRoot ? (
                  "Create root account"
                ) : (
                  "Sign Up"
                )}
              </Button>
              <p className="text-sm text-center text-muted-foreground">
                Already have an account?{" "}
                <Link
                  href="/login"
                  className="text-primary hover:underline font-medium"
                >
                  Sign in
                </Link>
              </p>
            </CardFooter>
          </form>
        </Card>
      </main>
    </div>
  );
}
