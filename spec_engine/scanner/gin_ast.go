// gin_ast.go — Go AST route extractor for Gin/Echo applications.
//
// Reads a Go source file path from os.Args[1], parses it with go/ast,
// and writes a JSON array of route objects to stdout.
//
// Each route object:
//   {"method": "GET", "path": "/v1/accounts", "handler": "listAccounts", "line": 12}
//
// Gin path params use :name syntax; this tool converts them to {name}.
// Group paths are resolved by walking the AST for Group() calls.
//
// Build: go build -o gin_ast_tool gin_ast.go
// Usage: ./gin_ast_tool path/to/main.go

package main

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strings"
)

type Route struct {
	Method  string `json:"method"`
	Path    string `json:"path"`
	Handler string `json:"handler"`
	Line    int    `json:"line"`
}

var httpMethods = map[string]bool{
	"GET": true, "POST": true, "PUT": true, "DELETE": true,
	"PATCH": true, "HEAD": true, "OPTIONS": true,
}

func normalizePath(p string) string {
	// Convert :param → {param}
	parts := strings.Split(p, "/")
	for i, part := range parts {
		if strings.HasPrefix(part, ":") {
			parts[i] = "{" + part[1:] + "}"
		}
	}
	result := strings.Join(parts, "/")
	if !strings.HasPrefix(result, "/") {
		result = "/" + result
	}
	return result
}

func joinPath(base, suffix string) string {
	base = strings.TrimRight(base, "/")
	suffix = strings.TrimLeft(suffix, "/")
	if suffix == "" {
		return base
	}
	return base + "/" + suffix
}

func extractStringLit(expr ast.Expr) string {
	if lit, ok := expr.(*ast.BasicLit); ok && lit.Kind == token.STRING {
		s := lit.Value
		if len(s) >= 2 {
			return s[1 : len(s)-1] // strip quotes
		}
	}
	return ""
}

func extractFuncName(expr ast.Expr) string {
	switch e := expr.(type) {
	case *ast.Ident:
		return e.Name
	case *ast.SelectorExpr:
		return e.Sel.Name
	case *ast.FuncLit:
		return "func"
	}
	return "anonymous"
}

type Walker struct {
	fset   *token.FileSet
	routes []Route
	prefix string // current group prefix
}

func (w *Walker) Visit(node ast.Node) ast.Visitor {
	callExpr, ok := node.(*ast.CallExpr)
	if !ok {
		return w
	}

	sel, ok := callExpr.Fun.(*ast.SelectorExpr)
	if !ok {
		return w
	}

	method := strings.ToUpper(sel.Sel.Name)

	// router.Group("/prefix", ...) — enter new prefix context
	if method == "GROUP" && len(callExpr.Args) >= 1 {
		groupPath := extractStringLit(callExpr.Args[0])
		newPrefix := normalizePath(joinPath(w.prefix, groupPath))
		subWalker := &Walker{fset: w.fset, prefix: newPrefix}
		// Walk remaining args (callback function body)
		for _, arg := range callExpr.Args[1:] {
			ast.Walk(subWalker, arg)
		}
		w.routes = append(w.routes, subWalker.routes...)
		return nil // don't walk args again
	}

	// router.GET("/path", handler)
	if httpMethods[method] && len(callExpr.Args) >= 2 {
		routePath := extractStringLit(callExpr.Args[0])
		if routePath == "" {
			return w
		}
		fullPath := normalizePath(joinPath(w.prefix, routePath))
		handler := extractFuncName(callExpr.Args[len(callExpr.Args)-1])
		pos := w.fset.Position(callExpr.Pos())
		w.routes = append(w.routes, Route{
			Method:  method,
			Path:    fullPath,
			Handler: handler,
			Line:    pos.Line,
		})
	}

	return w
}

func main() {
	if len(os.Args) < 2 {
		os.Stdout.WriteString("[]")
		return
	}

	filePath := os.Args[1]
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filePath, nil, 0)
	if err != nil {
		os.Stdout.WriteString("[]")
		return
	}

	walker := &Walker{fset: fset, prefix: ""}
	ast.Walk(walker, f)

	out, err := json.Marshal(walker.routes)
	if err != nil {
		os.Stdout.WriteString("[]")
		return
	}
	os.Stdout.Write(out)
}
