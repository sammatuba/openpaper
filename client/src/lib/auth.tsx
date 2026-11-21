"use client"

import { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { ShieldX } from 'lucide-react';
import { endProjectSession } from '@/hooks/useProjects';
import { fetchFromApi } from './api';

export interface BasicUser {
	name: string;
	picture: string;
	id?: string;
}

export interface User extends BasicUser {
	id: string;
	email: string;
	is_active: boolean;
	is_blocked: boolean;
}

interface AuthContextType {
	user: User | null;
	loading: boolean;
	error: string | null;
	login: () => Promise<void>;
	logout: (allDevices?: boolean) => Promise<void>;
}

const AUTH_STORAGE_KEY = 'auth_user';
// Tabs tell each other when the user signs out, so none keeps showing the account that left.
const AUTH_CHANNEL = 'openpaper-auth';
const SIGNED_OUT = 'signed-out';
const announceSignOut = () => {
	if (typeof BroadcastChannel === 'undefined') return;
	const channel = new BroadcastChannel(AUTH_CHANNEL);
	channel.postMessage(SIGNED_OUT);
	channel.close();
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
	// Always initialize to null to match server render and avoid hydration mismatch.
	// localStorage is read in the effect below for fast optimistic state.
	const [user, setUser] = useState<User | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// Sync user state with localStorage whenever it changes
	useEffect(() => {
		if (user) {
			localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
		} else {
			localStorage.removeItem(AUTH_STORAGE_KEY);
		}
	}, [user]);

	// Counts changes of identity. An answer to "who am I" that was asked before the
	// latest change is ignored, so a slow one cannot sign a user back in.
	const identity = useRef(0);
	const checkAuth = useRef(async () => {});

	// Another tab signed out: this one drops the user and everything cached for them.
	useEffect(() => {
		if (typeof BroadcastChannel === 'undefined') return;
		const channel = new BroadcastChannel(AUTH_CHANNEL);
		channel.onmessage = event => {
			if (event.data === SIGNED_OUT) {
				identity.current++;
				void endProjectSession();
				setUser(null);
				return;
			}
			// Another tab is now signed in as someone else: drop this tab's cache and ask who we are.
			const other = (event.data as { user?: string } | null)?.user;
			if (other && cachedFor.current !== null && other !== cachedFor.current) {
				identity.current++;
				void endProjectSession();
				void checkAuth.current();
			}
		};
		return () => channel.close();
	}, []);

	// The cache belongs to one user. If the signed-in user changes or leaves by
	// any route, what was cached for the previous one is dropped.
	const cachedFor = useRef<string | null>(null);
	useEffect(() => {
		const id = user?.id ?? null;
		if (cachedFor.current !== null && cachedFor.current !== id) void endProjectSession();
		if (id !== null && cachedFor.current !== id && typeof BroadcastChannel !== 'undefined') {
			const channel = new BroadcastChannel(AUTH_CHANNEL);
			channel.postMessage({ user: id });
			channel.close();
		}
		cachedFor.current = id;
	}, [user?.id]);

	// Check if user is logged in
	useEffect(() => {
		// Immediately restore cached user for fast UI update
		const storedUser = localStorage.getItem(AUTH_STORAGE_KEY);
		if (storedUser) {
			try {
				setUser(JSON.parse(storedUser));
			} catch {
				localStorage.removeItem(AUTH_STORAGE_KEY);
			}
		}

		checkAuth.current = async () => {
			const asked = identity.current;
			try {
				const response = await fetchFromApi('/api/auth/me');
				if (asked !== identity.current) return;
				if (response.success && response.user) {
					setUser(response.user);
				} else {
					// Auth check failed, clear the user
					setUser(null);
				}
			} catch (err) {
				if (asked !== identity.current) return;
				console.error('Auth check failed:', err);
				setError('Failed to check authentication status');
				// Also clear the user on error
				setUser(null);
			} finally {
				setLoading(false);
			}
		};

		void checkAuth.current();
	}, []);

	// Start Google login flow
	const login = async () => {
		try {
			setLoading(true);
			const response = await fetchFromApi('/api/auth/google/login');
			if (response.auth_url) {
				// Store the page the user was trying to reach as the post-login
				// return location. RequireAuth redirects unauthenticated users to
				// /login?returnTo=<path>, so prefer that param; fall back to the
				// current path for users who opened /login directly.
				const params = new URLSearchParams(window.location.search);
				const returnTo = params.get('returnTo') || window.location.pathname;
				localStorage.setItem('returnTo', returnTo);
				// Redirect to Google OAuth
				window.location.href = response.auth_url;
			}
		} catch (err) {
			console.error('Login failed:', err);
			setError('Failed to start login process');
		} finally {
			setLoading(false);
		}
	};

	// Logout user
	const logout = async (allDevices = false) => {
		try {
			setLoading(true);
			await fetchFromApi(`/api/auth/logout?all_devices=${allDevices}`);
			identity.current++;
			setUser(null);
			// Cached responses belong to the user who just left.
			await endProjectSession();
			announceSignOut();
		} catch (err) {
			console.error('Logout failed:', err);
			setError('Failed to logout');
		} finally {
			setLoading(false);
		}
	};

	if (!loading && user?.is_blocked) {
		return (
			<AuthContext.Provider value={{ user, loading, error, login, logout }}>
				<div className="flex items-center justify-center h-screen p-4">
					<div className="w-full max-w-lg text-center space-y-4">
						<div className="mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-900/30 p-4 w-fit">
							<ShieldX className="h-8 w-8 text-red-600 dark:text-red-400" />
						</div>
						<h1 className="text-2xl font-bold">Account Suspended</h1>
						<p className="text-muted-foreground">
							Your account has been flagged and suspended for suspected misconduct
							of the platform.
						</p>
						<p className="text-muted-foreground">
							If you believe this is an error, please contact us at{" "}
							<a href="mailto:team@khoj.dev" className="text-primary hover:underline font-medium">
								team@khoj.dev
							</a>{" "}
							and we will review your account.
						</p>
						<button
							onClick={() => logout()}
							className="mt-4 inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
						>
							Sign out
						</button>
					</div>
				</div>
			</AuthContext.Provider>
		);
	}

	return (
		<AuthContext.Provider value={{ user, loading, error, login, logout }}>
			{children}
		</AuthContext.Provider>
	);
}

export function useAuth() {
	const context = useContext(AuthContext);
	if (context === undefined) {
		throw new Error('useAuth must be used within an AuthProvider');
	}
	return context;
}
