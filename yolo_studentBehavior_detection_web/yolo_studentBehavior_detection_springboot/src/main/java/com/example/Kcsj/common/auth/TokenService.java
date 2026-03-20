package com.example.Kcsj.common.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

@Component
public class TokenService {
    private static final String HMAC_ALGO = "HmacSHA256";
    private static final SecureRandom RANDOM = new SecureRandom();

    @Value("${app.auth.secret:replace-this-in-production}")
    private String secret;

    @Value("${app.auth.token-ttl-ms:604800000}")
    private long ttlMs;

    public String issueToken(String username, String role) {
        long expireAt = System.currentTimeMillis() + Math.max(ttlMs, 60000L);
        String nonce = Long.toHexString(RANDOM.nextLong());
        String payload = safe(username) + "\n" + safe(role) + "\n" + expireAt + "\n" + nonce;
        String payloadBase64 = base64UrlEncode(payload.getBytes(StandardCharsets.UTF_8));
        String signature = sign(payloadBase64);
        return payloadBase64 + "." + signature;
    }

    public AuthUser verifyToken(String authHeader) {
        String token = extractToken(authHeader);
        if (token == null) {
            return null;
        }

        String[] parts = token.split("\\.");
        if (parts.length != 2) {
            return null;
        }

        String payloadBase64 = parts[0];
        String signature = parts[1];
        String expected = sign(payloadBase64);
        if (!constantTimeEquals(signature, expected)) {
            return null;
        }

        String payload;
        try {
            payload = new String(Base64.getUrlDecoder().decode(payloadBase64), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException ex) {
            return null;
        }

        String[] fields = payload.split("\\n", -1);
        if (fields.length != 4) {
            return null;
        }

        String username = fields[0];
        String role = fields[1];
        long expireAt;
        try {
            expireAt = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            return null;
        }

        if (System.currentTimeMillis() > expireAt) {
            return null;
        }

        if (username.isEmpty() || role.isEmpty()) {
            return null;
        }

        return new AuthUser(username, role);
    }

    private String extractToken(String authHeader) {
        if (authHeader == null) {
            return null;
        }
        String raw = authHeader.trim();
        if (raw.isEmpty()) {
            return null;
        }
        if (raw.regionMatches(true, 0, "Bearer ", 0, 7)) {
            raw = raw.substring(7).trim();
        }
        return raw.isEmpty() ? null : raw;
    }

    private String sign(String payloadBase64) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGO);
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), HMAC_ALGO));
            byte[] digest = mac.doFinal(payloadBase64.getBytes(StandardCharsets.UTF_8));
            return base64UrlEncode(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("token sign failed", ex);
        }
    }

    private String safe(String value) {
        return value == null ? "" : value.replace("\n", "").trim();
    }

    private String base64UrlEncode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private boolean constantTimeEquals(String a, String b) {
        return MessageDigest.isEqual(
                a == null ? new byte[0] : a.getBytes(StandardCharsets.UTF_8),
                b == null ? new byte[0] : b.getBytes(StandardCharsets.UTF_8)
        );
    }
}
