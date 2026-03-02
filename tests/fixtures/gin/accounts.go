package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	v1 := r.Group("/v1")
	{
		accounts := v1.Group("/accounts")
		{
			accounts.GET("", listAccounts)
			accounts.GET("/:accountId", getAccount)
			accounts.POST("", createAccount)
			accounts.PUT("/:accountId", updateAccount)
			accounts.DELETE("/:accountId", deleteAccount)
		}
	}

	r.Run(":8080")
}

func listAccounts(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{})
}

func getAccount(c *gin.Context) {
	accountId := c.Param("accountId")
	c.JSON(http.StatusOK, gin.H{"id": accountId})
}

func createAccount(c *gin.Context) {
	c.JSON(http.StatusCreated, gin.H{})
}

func updateAccount(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{})
}

func deleteAccount(c *gin.Context) {
	c.Status(http.StatusNoContent)
}
