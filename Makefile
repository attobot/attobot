publish-AttoBot:
publish-AttoBotDeleter:

publish-%: %/lambda_function.py
	-rm tmp.zip
	zip -j tmp.zip $^
	aws lambda update-function-code --function-name $* --zip-file "fileb://tmp.zip"
	-rm tmp.zip

.PHONY: publish-%
