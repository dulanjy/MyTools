package com.example.Kcsj.common.auth;

public class AuthUser {
    private final String username;
    private final String role;

    public AuthUser(String username, String role) {
        this.username = username;
        this.role = role;
    }

    public String getUsername() {
        return username;
    }

    public String getRole() {
        return role;
    }
}
