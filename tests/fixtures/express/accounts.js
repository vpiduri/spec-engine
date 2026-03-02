const express = require('express');
const router = express.Router();

router.get('/v1/accounts', (req, res) => {
    res.json([]);
});

router.get('/v1/accounts/:accountId', (req, res) => {
    const { accountId } = req.params;
    res.json({ id: accountId });
});

router.post('/v1/accounts', (req, res) => {
    const body = req.body;
    res.status(201).json({});
});

router.put('/v1/accounts/:accountId', (req, res) => {
    res.json({});
});

router.delete('/v1/accounts/:accountId', (req, res) => {
    res.status(204).send();
});

module.exports = router;
