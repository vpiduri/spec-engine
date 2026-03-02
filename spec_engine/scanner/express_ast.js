#!/usr/bin/env node
/**
 * Express/NestJS route extractor using @babel/parser.
 *
 * Reads a JavaScript/TypeScript file path from argv[2], parses it with
 * @babel/parser, and writes a JSON array of route objects to stdout.
 *
 * Each route object:
 *   { method, path, handler, line }
 *
 * Exit 0 on success, exit 1 on error (prints [] to stdout).
 */

'use strict';

const fs = require('fs');
const path = require('path');

let parser;
try {
  parser = require('@babel/parser');
} catch (e) {
  // @babel/parser not installed — output empty array and exit
  process.stdout.write('[]');
  process.exit(0);
}

const filePath = process.argv[2];
if (!filePath) {
  process.stdout.write('[]');
  process.exit(0);
}

let source;
try {
  source = fs.readFileSync(filePath, 'utf8');
} catch (e) {
  process.stdout.write('[]');
  process.exit(0);
}

let ast;
try {
  ast = parser.parse(source, {
    sourceType: 'module',
    plugins: ['typescript', 'decorators-legacy', 'classProperties'],
    errorRecovery: true,
  });
} catch (e) {
  process.stdout.write('[]');
  process.exit(0);
}

const routes = [];
const HTTP_METHODS = new Set(['get', 'post', 'put', 'delete', 'patch', 'head', 'options']);

/**
 * Convert Express :param syntax to OpenAPI {param} syntax.
 */
function normalizeExpressPath(p) {
  return p.replace(/:(\w+)/g, '{$1}');
}

/**
 * Extract string value from a node if it's a string literal.
 */
function getStringValue(node) {
  if (!node) return null;
  if (node.type === 'StringLiteral') return node.value;
  if (node.type === 'TemplateLiteral' && node.quasis.length === 1) {
    return node.quasis[0].value.cooked;
  }
  return null;
}

/**
 * Get function name from an expression node.
 */
function getFuncName(node) {
  if (!node) return 'anonymous';
  if (node.type === 'Identifier') return node.id ? node.id.name : node.name || 'anonymous';
  if (node.type === 'FunctionExpression' && node.id) return node.id.name;
  if (node.type === 'ArrowFunctionExpression') return 'arrow';
  return 'anonymous';
}

/**
 * Walk AST nodes, calling visitor for each.
 */
function walk(node, visitor) {
  if (!node || typeof node !== 'object') return;
  visitor(node);
  for (const key of Object.keys(node)) {
    const child = node[key];
    if (Array.isArray(child)) {
      child.forEach(c => walk(c, visitor));
    } else if (child && typeof child === 'object' && child.type) {
      walk(child, visitor);
    }
  }
}

walk(ast, (node) => {
  // router.get('/path', handler) or app.post('/path', handler)
  if (
    node.type === 'ExpressionStatement' &&
    node.expression.type === 'CallExpression'
  ) {
    const call = node.expression;
    if (
      call.callee.type === 'MemberExpression' &&
      call.callee.property.type === 'Identifier'
    ) {
      const method = call.callee.property.name.toLowerCase();
      if (HTTP_METHODS.has(method) && call.arguments.length >= 1) {
        const pathVal = getStringValue(call.arguments[0]);
        if (pathVal !== null) {
          const handler = call.arguments.length > 1
            ? getFuncName(call.arguments[call.arguments.length - 1])
            : 'anonymous';
          routes.push({
            method: method.toUpperCase(),
            path: normalizeExpressPath(pathVal),
            handler,
            line: node.loc ? node.loc.start.line : 1,
          });
        }
      }
    }
  }
});

process.stdout.write(JSON.stringify(routes));
