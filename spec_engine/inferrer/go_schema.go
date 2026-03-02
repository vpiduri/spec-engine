// go_schema.go — Go struct schema extractor.
//
// Reads: argv[1] = Go source file path, argv[2] = struct name to extract.
// Writes a JSON Schema object to stdout.
//
// Struct tags parsed:
//   json:"name,omitempty"    → field name + optional
//   validate:"required"      → required field
//   validate:"min=1,max=100" → minimum / maximum
//
// Build: go build -o go_schema_tool go_schema.go
// Usage: ./go_schema_tool path/to/models.go MyStruct

package main

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"reflect"
	"strconv"
	"strings"
)

type JSONSchema map[string]interface{}

func goTypeToSchema(typeName string) JSONSchema {
	switch typeName {
	case "string":
		return JSONSchema{"type": "string"}
	case "bool":
		return JSONSchema{"type": "boolean"}
	case "int", "int8", "int16", "int32", "uint", "uint8", "uint16", "uint32", "byte", "rune":
		return JSONSchema{"type": "integer"}
	case "int64", "uint64":
		return JSONSchema{"type": "integer", "format": "int64"}
	case "float32":
		return JSONSchema{"type": "number", "format": "float"}
	case "float64":
		return JSONSchema{"type": "number", "format": "double"}
	case "Time":
		return JSONSchema{"type": "string", "format": "date-time"}
	}
	// Named type — use $ref
	return JSONSchema{"$ref": "#/components/schemas/" + typeName}
}

func parseStructTag(tag string) (jsonName string, omitempty bool, required bool, min, max *float64) {
	// Unquote the full struct tag
	unquoted := strings.Trim(tag, "`")

	// Extract json tag
	st := reflect.StructTag(unquoted)
	jsonTag := st.Get("json")
	parts := strings.Split(jsonTag, ",")
	if len(parts) > 0 && parts[0] != "" && parts[0] != "-" {
		jsonName = parts[0]
	}
	for _, p := range parts[1:] {
		if p == "omitempty" {
			omitempty = true
		}
	}

	// Extract validate tag
	validateTag := st.Get("validate")
	for _, rule := range strings.Split(validateTag, ",") {
		rule = strings.TrimSpace(rule)
		if rule == "required" {
			required = true
		}
		if strings.HasPrefix(rule, "min=") {
			if v, err := strconv.ParseFloat(rule[4:], 64); err == nil {
				min = &v
			}
		}
		if strings.HasPrefix(rule, "max=") {
			if v, err := strconv.ParseFloat(rule[4:], 64); err == nil {
				max = &v
			}
		}
	}
	return
}

func extractTypeExpr(expr ast.Expr) string {
	switch t := expr.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return extractTypeExpr(t.X) // pointer → treat as optional of inner type
	case *ast.ArrayType:
		return "[]" + extractTypeExpr(t.Elt)
	case *ast.MapType:
		return "map[...]" + extractTypeExpr(t.Value)
	case *ast.SelectorExpr:
		// e.g., time.Time
		return t.Sel.Name
	}
	return "interface{}"
}

func main() {
	if len(os.Args) < 3 {
		os.Stdout.WriteString("{}")
		return
	}

	filePath := os.Args[1]
	structName := os.Args[2]

	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filePath, nil, 0)
	if err != nil {
		os.Stdout.WriteString("{}")
		return
	}

	for _, decl := range f.Decls {
		genDecl, ok := decl.(*ast.GenDecl)
		if !ok {
			continue
		}
		for _, spec := range genDecl.Specs {
			typeSpec, ok := spec.(*ast.TypeSpec)
			if !ok || typeSpec.Name.Name != structName {
				continue
			}
			structType, ok := typeSpec.Type.(*ast.StructType)
			if !ok {
				continue
			}

			properties := map[string]JSONSchema{}
			required := []string{}

			for _, field := range structType.Fields.List {
				if len(field.Names) == 0 {
					continue // embedded
				}

				fieldName := field.Names[0].Name
				if !ast.IsExported(fieldName) {
					continue
				}

				typeName := extractTypeExpr(field.Type)
				isPointer := false
				if starExpr, ok := field.Type.(*ast.StarExpr); ok {
					_ = starExpr
					isPointer = true
				}

				jsonName := ""
				omitempty := false
				isRequired := false
				var minVal, maxVal *float64

				if field.Tag != nil {
					jsonName, omitempty, isRequired, minVal, maxVal = parseStructTag(field.Tag.Value)
				}
				if jsonName == "" {
					// Convert Go field name to camelCase heuristic
					jsonName = strings.ToLower(fieldName[:1]) + fieldName[1:]
				}

				var schema JSONSchema
				if strings.HasPrefix(typeName, "[]") {
					inner := typeName[2:]
					innerSchema := goTypeToSchema(inner)
					schema = JSONSchema{"type": "array", "items": innerSchema}
				} else if strings.HasPrefix(typeName, "map[...]") {
					inner := typeName[8:]
					innerSchema := goTypeToSchema(inner)
					schema = JSONSchema{"type": "object", "additionalProperties": innerSchema}
				} else {
					schema = goTypeToSchema(typeName)
				}

				if isPointer || omitempty {
					schema["nullable"] = true
				}
				if minVal != nil {
					schema["minimum"] = *minVal
				}
				if maxVal != nil {
					schema["maximum"] = *maxVal
				}

				properties[jsonName] = schema

				if isRequired && !isPointer && !omitempty {
					required = append(required, jsonName)
				}
			}

			result := JSONSchema{
				"type":       "object",
				"properties": properties,
			}
			if len(required) > 0 {
				result["required"] = required
			}

			out, err := json.Marshal(result)
			if err != nil {
				os.Stdout.WriteString("{}")
				return
			}
			os.Stdout.Write(out)
			return
		}
	}

	os.Stdout.WriteString("{}")
}
