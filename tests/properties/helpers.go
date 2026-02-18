package properties

// findResourceBlockEnd finds the end of a resource block in Terraform configuration
func findResourceBlockEnd(content string, startPos int) int {
	// If startPos is invalid, return -1
	if startPos == -1 {
		return -1
	}

	braceCount := 0
	inBlock := false

	for i := startPos; i < len(content); i++ {
		char := content[i]

		if char == '{' {
			braceCount++
			inBlock = true
		} else if char == '}' {
			braceCount--
			if inBlock && braceCount == 0 {
				return i
			}
		}
	}

	return -1
}

// findNestedBlockEnd finds the end of a nested block in Terraform configuration
func findNestedBlockEnd(content string, startPos int) int {
	// If startPos is invalid, return -1
	if startPos == -1 {
		return -1
	}

	braceCount := 0
	inBlock := false

	for i := startPos; i < len(content); i++ {
		char := content[i]

		if char == '{' {
			braceCount++
			inBlock = true
		} else if char == '}' {
			braceCount--
			if inBlock && braceCount == 0 {
				return i
			}
		}
	}

	return -1
}
