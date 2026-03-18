package com.example.Kcsj.common;

import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import javax.servlet.http.HttpServletRequest;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result<Void> handleValidation(MethodArgumentNotValidException ex, HttpServletRequest request) {
        String msg = ex.getBindingResult().getAllErrors().isEmpty()
                ? "参数校验失败"
                : ex.getBindingResult().getAllErrors().get(0).getDefaultMessage();
        return Result.error(-1, attachPath(request, msg));
    }

    @ExceptionHandler(Exception.class)
    public Result<Void> handleAny(Exception ex, HttpServletRequest request) {
        return Result.error(-1, attachPath(request, ex.getMessage()));
    }

    private String attachPath(HttpServletRequest request, String msg) {
        String path = request == null ? "" : request.getRequestURI();
        String safeMsg = (msg == null || msg.trim().isEmpty()) ? "服务器内部错误" : msg;
        return path.isEmpty() ? safeMsg : ("[" + path + "] " + safeMsg);
    }
}
