package com.example.demo.controller;

import com.example.demo.model.CreateAccountRequest;
import com.example.demo.model.AccountResponse;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@RestController
@RequestMapping("/v1/accounts")
public class AccountController {

    @GetMapping
    public List<AccountResponse> listAccounts(
            @RequestParam(required = false) String status) {
        return null;
    }

    @GetMapping("/{accountId}")
    public AccountResponse getAccount(@PathVariable String accountId) {
        return null;
    }

    @PostMapping
    @PreAuthorize("hasAuthority('SCOPE_accounts:write')")
    public ResponseEntity<AccountResponse> createAccount(
            @RequestBody CreateAccountRequest request) {
        return null;
    }

    @PutMapping("/{accountId}")
    public AccountResponse updateAccount(
            @PathVariable String accountId,
            @RequestBody CreateAccountRequest request) {
        return null;
    }

    @DeleteMapping("/{accountId}")
    public void deleteAccount(@PathVariable String accountId) {
    }
}
