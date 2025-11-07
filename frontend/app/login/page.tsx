"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
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
import { AlertCircle, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const loginMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: async (data) => {
      // Save token first so it's available for subsequent requests
      localStorage.setItem("auth_token", data.access_token);

      // Get user info with the token now in localStorage
      const userResponse = await authApi.getProfile(data.access_token);
      setAuth(data.access_token, userResponse);
      router.push("/dashboard");
    },
    onError: (error: any) => {
      setError(formatApiError(error));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    loginMutation.mutate({ username, password });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-3xl font-bold text-center">
            Welcome to Doc2MD
          </CardTitle>
          <CardDescription className="text-center">
            Enter your credentials to access your account
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive flex items-start gap-2 animate-in slide-in-from-top-2">
                <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">Login Failed</p>
                  <p className="text-xs mt-1 opacity-90">{error}</p>
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="username">Username or Email</Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username or email"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  if (error) setError("");
                }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError("");
                }}
                required
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col space-y-4">
            <Button
              type="submit"
              className="w-full"
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign In"
              )}
            </Button>
            <p className="text-sm text-center text-muted-foreground">
              Don&apos;t have an account?{" "}
              <Link
                href="/register"
                className="text-primary hover:underline font-medium"
              >
                Sign up
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
