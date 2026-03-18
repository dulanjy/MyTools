package com.example.Kcsj.common;

import java.time.OffsetDateTime;
import java.util.UUID;

public class Result<T> {
    private int code;
    private String message;
    private T data;
    private String traceId;
    private String timestamp;

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    // Backward-compatible alias for old frontend fields.
    public String getMsg() {
        return message;
    }

    public void setMsg(String msg) {
        this.message = msg;
    }

    public String getTraceId() {
        return traceId;
    }

    public void setTraceId(String traceId) {
        this.traceId = traceId;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(String timestamp) {
        this.timestamp = timestamp;
    }

    public Result() {}

    public Result(T data) {
        this.data = data;
    }

    public static Result<Void> success() {
        Result<Void> result = new Result<>();
        result.setCode(0);
        result.setMessage("success");
        result.setTraceId(newTraceId());
        result.setTimestamp(OffsetDateTime.now().toString());
        return result;
    }

    public static <T> Result<T> success(T data) {
        Result<T> result = new Result<>(data);
        result.setCode(0);
        result.setMessage("success");
        result.setTraceId(newTraceId());
        result.setTimestamp(OffsetDateTime.now().toString());
        return result;
    }

    public static Result<Void> error(int code, String message) {
        Result<Void> result = new Result<>();
        result.setCode(code);
        result.setMessage(message);
        result.setTraceId(newTraceId());
        result.setTimestamp(OffsetDateTime.now().toString());
        return result;
    }

    private static String newTraceId() {
        return UUID.randomUUID().toString().replace("-", "");
    }
}
