package main

import (
	"fmt"
	"math/rand"
)

func main() {
	fmt.Println(rand.Perm(16)[:16])
}