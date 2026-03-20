package com.example.Kcsj.common.auth;

public final class AuthContext {
    private static final ThreadLocal<AuthUser> CURRENT = new ThreadLocal<>();

    private AuthContext() {
    }

    public static void setCurrentUser(AuthUser authUser) {
        CURRENT.set(authUser);
    }

    public static AuthUser getCurrentUser() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
