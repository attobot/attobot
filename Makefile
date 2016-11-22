
publish-lambda: lambda_function.py
	-rm attobot.zip
	zip attobot.zip $^
	aws lambda update-function-code --function-name AttoBot --zip-file "fileb://attobot.zip" --publish
	-rm attobot.zip

.PHONY: publish-lambda
